# -*- coding: utf-8 -*-

import logging

from odoo import api
from odoo.addons.payment.models import payment_token
from odoo.addons.sale.models import sale_order

from monero import MoneroIncomingTransfer, MoneroUtils

from ..models.exceptions import NoTXFound, NumConfirmationsNotMet, MoneroAddressReuse, MoneroTransactionUpdateJobError
from ..models.exceptions import MoneroPaymentAcquirerRPCUnauthorized
from ..models.exceptions import MoneroPaymentAcquirerRPCSSLError

_logger = logging.getLogger(__name__)


class MoneroWalletIncomingTransfers:
    amount: int
    num_confirmations: int
    transfers: list[MoneroIncomingTransfer]

    def __init__(self, transfers: list[MoneroIncomingTransfer]) -> None:
        self.transfers = transfers
        self.amount = 0
        self.num_confirmations = 0

        num_confirmations: int | None = None

        for transfer in transfers:
            if transfer.amount is None:
                continue
            
            fee = transfer.tx.fee if transfer.tx.fee is not None else 0
            self.amount += transfer.amount - fee

            if num_confirmations is None:
                num_confirmations = transfer.tx.num_confirmations
            elif transfer.tx.num_confirmations is not None and transfer.tx.num_confirmations < num_confirmations:
                num_confirmations = transfer.tx.num_confirmations

        if num_confirmations is not None:
            self.num_confirmations = num_confirmations

        _logger.warning(f"NUM CONFIRMATIONS {self.num_confirmations}")
        if len(transfers) > 0:
            transfer = transfers[0]
            _logger.warning(f"TX CONFS: {transfer.tx.num_confirmations}")

class MoneroSalesOrder(sale_order.SaleOrder):

    _inherit = "sale.order"

    # region Missing

    id: str

    # endregion

    @classmethod
    def _get_address_transfers(cls, transaction, address: str) -> MoneroWalletIncomingTransfers:
        try:
            transfers = transaction.acquirer_id.get_incoming_unconfirmed_transfers(address)

            return MoneroWalletIncomingTransfers(transfers)

        except MoneroPaymentAcquirerRPCUnauthorized:
            raise MoneroPaymentAcquirerRPCUnauthorized(
                "Monero Processing Queue: "
                "Monero Payment Acquirer "
                "can't authenticate with RPC "
                "due to user name or password"
            )
        except MoneroPaymentAcquirerRPCSSLError:
            raise MoneroPaymentAcquirerRPCSSLError(
                "Monero Processing Queue: Monero Payment Acquirer "
                "experienced an SSL Error with RPC"
            )
        except Exception as e:
            raise Exception(
                f"Monero Processing Queue: Monero Payment Acquirer "
                f"experienced an Error with RPC: {e}"
            )

    @api.model
    def update_transaction(self, transaction, token: payment_token.PaymentToken, num_confirmation_required: int) -> None:
        _logger.warning("------- CHECKPOINT UPDATE TRANSACTION")

        # update deposit amount
        incoming_transfers = self._get_address_transfers(transaction, str(token.name))
        transaction.amount_paid_xmr = MoneroUtils.atomic_units_to_xmr(incoming_transfers.amount)
        amount_paid = transaction.get_amount_paid_xmr()
        amount = transaction.get_amount_xmr()
        remaining_xmr = (amount - amount_paid) if amount_paid <= amount else 0
        transaction.amount_remaining_xmr = remaining_xmr
        transaction.fully_paid = remaining_xmr == 0

        # update num of confirmations required
        if num_confirmation_required <= incoming_transfers.num_confirmations:
            transaction.confirmations_required = 0
        else:
            transaction.confirmations_required = num_confirmation_required - incoming_transfers.num_confirmations
        
        _logger.warning("------- TOTAL USD: {}".format(self.amount_total))
        _logger.warning("------- TOTAL XMR: {}".format(transaction.amount_xmr))
        _logger.warning("------- TOTAL LEFT TO PAY XMR: {}".format(transaction.amount_remaining_xmr))
        _logger.warning("------- CONFIRMATIONS REQUIRED: {}".format(transaction.confirmations_required))
        self.env.cr.commit()

        if not transaction.is_fully_paid():
            _logger.warning("-------- CONTINUE UPDATE TRANSACTION")
            raise MoneroTransactionUpdateJobError("Continue updating...")
        
        _logger.warning("-------- FINISHED UPDATE TRANSACTION")

    @api.model
    def process_transaction(self, transaction, token: payment_token.PaymentToken, num_confirmation_required: int):
        _logger.warning("------- CHECKPOINT PROCESS TRANSACTION ORDER")
        _logger.warning("------- TOTAL USD: {}".format(self.amount_total))
        _logger.warning("------- TOTAL XMR: {}".format(transaction.amount_xmr))
        _logger.warning("------- TOTAL LEFT TO PAY XMR: {}".format(transaction.amount_remaining_xmr))

        incoming_transfers = self._get_address_transfers(transaction, str(token.name))
        transfers = incoming_transfers.transfers

        _logger.warning("Incoming Payments: {}".format(len(transfers)))

        if len(transfers) == 0:
            job = (
                self.env["queue.job"]
                .sudo()
                .search([("uuid", "=", self.env.context.get("job_uuid"))])
            )
            _logger.info(job.max_retries)
            _logger.info(job.retry)
            if job.retry == job.max_retries - 1:
                self.action_cancel()
                self.write({"state": "cancel", "is_expired": "true"})
                log_msg = (
                    f"PaymentAcquirer: {transaction.acquirer_id.provider} "
                    f"Subaddress: {token.name} "
                    "Status: No transaction found. Too much time has passed, "
                    "customer has most likely not sent payment. "
                    f"Cancelling order # {self.id}. "
                    f"Action: Nothing"
                )
                _logger.warning(log_msg)
                return log_msg
            else:
                exception_msg = (
                    f"PaymentAcquirer: {transaction.acquirer_id.provider} "
                    f"Subaddress: {token.name} "
                    "Status: No transaction found. "
                    "TX probably hasn't been added to a block or mem-pool yet. "
                    "This is fine. "
                    f"Another job will execute. Action: Nothing"
                )
                raise NoTXFound(exception_msg)

        if len(transfers) > 1:
            # TODO custom logic if the end user sends
            #  multiple transactions for one order
            # this would involve creating another "payment.transaction"
            # and notifying both the buyer and seller
            raise MoneroAddressReuse(
                f"PaymentAcquirer: {transaction.acquirer_id.provider} "
                f"Subaddress: {token.name} "
                "Status: Address reuse found. "
                "The end user most likely sent "
                "multiple transactions for a single order. "
                "Action: Reconcile transactions manually"
            )

        if len(transfers) == 1:
            this_payment = transfers.pop()

            conf_err_msg = (
                f"PaymentAcquirer: {transaction.acquirer_id.provider} "
                f"Subaddress: {token.name} "
                "Status: Waiting for more confirmations "
                f"Confirmations: current {this_payment.tx.num_confirmations}, "
                f"expected {num_confirmation_required} "
                "Action: none"
            )
            # TODO set transaction state to "authorized" once a monero transaction is
            #  found within the transaction pool
            # note that when the NumConfirmationsNotMet is raised any database commits
            # are lost
            _logger.warning(f"Number of confirmations required: {num_confirmation_required}, tx confirmations: {this_payment.tx.num_confirmations}, transaction confs: {transaction.confirmations_required}")
            if this_payment.tx.num_confirmations is None:
                if num_confirmation_required > 0:
                    raise NumConfirmationsNotMet(conf_err_msg)
            else:
                if this_payment.tx.num_confirmations < num_confirmation_required:
                    raise NumConfirmationsNotMet(conf_err_msg)
            payment_amount = this_payment.amount if this_payment.amount is not None else 0
            amount_to_pay: int = transaction.get_amount_xmr_atomic_units()
            payment_suffices: bool = payment_amount >= amount_to_pay
            
            _logger.info(f"Payment amount: {payment_amount}, amount to pay: {amount_to_pay}, payment suffices: {payment_suffices}")

            # need to convert, because this_payment.amount is of type decimal.Decimal...
            if payment_suffices:
                self.write({"state": "sale"})
                transaction._set_done()
                #transaction.write({"state": "done", "is_processed": "true"})
                _logger.info(
                    f"Monero payment recorded for sale order: {self.id}, "
                    f"associated with subaddress: {token.name}"
                )
                _logger.warning("amount: {}".format(self.amount_total))
                self.with_context(send_email=True).action_confirm()
                self._send_order_confirmation_mail()
                # TODO handle situation where the transaction amount is not equal
            else:
                _logger.warning("transaction amount was not equal")
