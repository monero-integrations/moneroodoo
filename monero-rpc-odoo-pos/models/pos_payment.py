from odoo import api, fields, models, _
from odoo.addons.point_of_sale.models import pos_payment

from monero import MoneroUtils

from ..utils import MoneroWalletIncomingTransfers

from .pos_payment_method import MoneroPosPaymentMethod
from .pos_order import MoneroPosOrder

from .exceptions import ( 
    NoTXFound, NumConfirmationsNotMet, MoneroAddressReuse, 
    MoneroTransactionUpdateJobError 
)


import logging

_logger = logging.getLogger(__name__)


class MoneroPosPayment(pos_payment.PosPayment):
    """
    OVERRIDING METHOD FROM
        odoo/addons/point_of_sale/models/pos_payment.py

    Used to register payments made in a pos.order.

    See `payment_ids` field of pos.order model.
    The main characteristics of pos.payment can be read from
    `payment_method_id`.
    """

    _inherit = "pos.payment"

    wallet_address = fields.Char("Payment Wallet Address")

    fully_paid = fields.Boolean(
        string="Fully Paid", help="Indicates if transaction is fully paid",
        default=False)

    currency_monero_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env['res.currency'].search([('name', '=', 'XMR')], limit=1).id)

    exchange_rate = fields.Monetary(
        string="Exchange Rate", currency_field='currency_id', readonly=True, required=True)

    amount_xmr = fields.Monetary(
        string="Amount XMR", currency_field='currency_monero_id', readonly=True, required=True)

    amount_remaining_xmr = fields.Monetary(
        string="Amount remaining to be paid XMR", currency_field='currency_monero_id', readonly=True, required=True)

    amount_paid_xmr = fields.Monetary(
        string="Amount paid XMR", currency_field='currency_monero_id', readonly=False, required=False,
        default=0)

    confirmations_required = fields.Integer(
        string="Number of network confirmations required", default = 0)
    
    # override
    payment_method_id: MoneroPosPaymentMethod
    pos_order_id: MoneroPosOrder


    def get_amount(self) -> float:
        return float(self.amount) # type: ignore

    def get_amount_xmr(self) -> float:
        return float(self.amount_xmr) # type: ignore
    
    def get_amount_paid_xmr(self) -> float:
        return float(self.amount_paid_xmr) # type: ignore

    def get_amount_remaining_xmr(self) -> float:
        return float(self.amount_remaining_xmr) # type: ignore

    def get_amount_xmr_atomic_units(self) -> int:
        return MoneroUtils.xmr_to_atomic_units(self.get_amount_xmr())

    def get_amount_paid_xmr_atomic_units(self) -> int:
        return MoneroUtils.xmr_to_atomic_units(self.get_amount_paid_xmr())
    
    def get_amount_remaining_xmr_atomic_units(self) -> int:
        return MoneroUtils.xmr_to_atomic_units(self.get_amount_remaining_xmr())

    def get_confirmations_required(self) -> int:
        return int(self.confirmations_required) # type: ignore

    def is_fully_paid(self) -> bool:
        return bool(self.fully_paid)

    def get_wallet_address(self) -> str:
        return str(self.wallet_address)

    def get_transfers(self) -> MoneroWalletIncomingTransfers:
        try:
            address: str = self.get_wallet_address()
            transfers = self.payment_method_id.get_incoming_unconfirmed_transfers(address)

            return MoneroWalletIncomingTransfers(transfers)
        except Exception as e:
            raise Exception(
                f"Monero Processing Queue: Monero Payment Acquirer "
                f"experienced an Error with RPC: {e}"
            )

    @api.model
    def update_transaction(self) -> None:
        _logger.warning("------- CHECKPOINT UPDATE TRANSACTION")

        # update deposit amount
        num_confirmation_required: int = self.payment_method_id.get_num_confirmations_required()
        incoming_transfers = self.get_transfers()
        self.amount_paid_xmr = MoneroUtils.atomic_units_to_xmr(incoming_transfers.amount)
        amount_paid = self.get_amount_paid_xmr()
        amount = self.get_amount_xmr()
        remaining_xmr = (amount - amount_paid) if amount_paid <= amount else 0
        self.amount_remaining_xmr = remaining_xmr
        self.fully_paid = remaining_xmr == 0

        # update num of confirmations required
        if num_confirmation_required <= incoming_transfers.num_confirmations:
            self.confirmations_required = 0
        else:
            self.confirmations_required = num_confirmation_required - incoming_transfers.num_confirmations
        
        _logger.warning("------- TOTAL USD: {}".format(self.get_amount()))
        _logger.warning("------- TOTAL XMR: {}".format(self.amount_xmr))
        _logger.warning("------- TOTAL LEFT TO PAY XMR: {}".format(self.amount_remaining_xmr))
        _logger.warning("------- CONFIRMATIONS REQUIRED: {}".format(self.confirmations_required))
        self.env.cr.commit()

        if not self.is_fully_paid() or int(self.confirmations_required) > 0:
            _logger.warning("-------- CONTINUE UPDATE TRANSACTION")
            raise MoneroTransactionUpdateJobError("Continue updating...")
        
        _logger.warning("-------- FINISHED UPDATE TRANSACTION")

    @api.model
    def process_transaction(self):
        _logger.warning("------- CHECKPOINT PROCESS TRANSACTION ORDER")
        transfers = self.get_transfers()
        
        if transfers.empty:
            job = (
                self.env["queue.job"]
                .sudo()
                .search([("uuid", "=", self.env.context.get("job_uuid"))])
            )
            _logger.info(job.max_retries)
            _logger.info(job.retry)
            if job.retry == job.max_retries - 1:
                self.write({"state": "cancel", "is_expired": "true"})
                log_msg = (
                    f"PaymentMethod: {self.payment_method_id.name} "
                    f"Subaddress: {self.wallet_address} "
                    "Status: No transaction found. Too much time has passed, "
                    "customer has most likely not sent payment. "
                    f"Cancelling order # {self.pos_order_id.id}. "
                    f"Action: Nothing"
                )
                _logger.warning(log_msg)
                return log_msg
            else:
                exception_msg = (
                    f"PaymentMethod: {self.payment_method_id.name} "
                    f"Subaddress: {self.wallet_address} "
                    "Status: No transaction found. "
                    "TX probably hasn't been added to a block or mem-pool yet. "
                    "This is fine. "
                    f"Another job will execute. Action: Nothing"
                )
                raise NoTXFound(exception_msg)

        if transfers.moreThanOne:
            # TODO custom logic if the end user sends
            #  multiple transactions for one order
            # this would involve creating another "payment.transaction"
            # and notifying both the buyer and seller
            raise MoneroAddressReuse(
                f"PaymentMethod: {self.payment_method_id.name} "
                f"Subaddress: {self.wallet_address} "
                "Status: Address reuse found. "
                "The end user most likely sent "
                "multiple transactions for a single order. "
                "Action: Reconcile transactions manually"
            )

        if transfers.onlyOne:
            this_payment = transfers.first
            if this_payment is None:
                raise NoTXFound("")
            
            num_confirmation_required = self.payment_method_id.get_num_confirmations_required()
            conf_err_msg = (
                f"PaymentMethod: {self.payment_method_id.name} "
                f"Subaddress: {self.wallet_address} "
                "Status: Waiting for more confirmations "
                f"Confirmations: current {this_payment.tx.num_confirmations}, "
                f"expected {num_confirmation_required} "
                "Action: none"
            )
            # TODO set transaction state to "authorized" once a monero transaction is
            #  found within the transaction pool
            # note that when the NumConfirmationsNotMe is raised any database commits
            # are lost
            if this_payment.tx.num_confirmations is None:
                if num_confirmation_required > 0:
                    raise NumConfirmationsNotMet(conf_err_msg)
            else:
                if this_payment.tx.num_confirmations < num_confirmation_required:
                    raise NumConfirmationsNotMet(conf_err_msg)

            payment_amount = this_payment.amount if this_payment.amount is not None else 0
            amount_to_pay: int = self.get_amount_xmr_atomic_units()
            payment_suffices: bool = payment_amount >= amount_to_pay

            if payment_suffices:
                self.pos_order_id.write({"state": "done"})
                self.write({"payment_status": "done"})
                _logger.info(
                    f"Monero payment recorded for pos order: {self.pos_order_id.id}, "
                    f"associated with subaddress: {self.wallet_address}"
                )
                # TODO handle situation where the transaction amount is not equal
