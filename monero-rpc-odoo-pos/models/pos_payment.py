from odoo import api, fields, models, _

from monero.wallet import Wallet
from .exceptions import NoTXFound, NumConfirmationsNotMet, MoneroAddressReuse
from .exceptions import MoneroPaymentMethodRPCUnauthorized
from .exceptions import MoneroPaymentMethodRPCSSLError

import logging

_logger = logging.getLogger(__name__)


class MoneroPosPayment(models.Model):
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

    def process_transaction(self):

        try:
            wallet: Wallet = self.payment_method_id.get_wallet()
        except MoneroPaymentMethodRPCUnauthorized:
            raise MoneroPaymentMethodRPCUnauthorized(
                "Monero Processing Queue: "
                "Monero Payment Acquirer "
                "can't authenticate with RPC "
                "due to user name or password"
            )
        except MoneroPaymentMethodRPCSSLError:
            raise MoneroPaymentMethodRPCSSLError(
                "Monero Processing Queue: Monero Payment Acquirer "
                "experienced an SSL Error with RPC"
            )
        except Exception as e:
            raise Exception(
                f"Monero Processing Queue: Monero Payment Acquirer "
                f"experienced an Error with RPC: {e.__class__.__name__}"
            )

        incoming_payment = wallet.incoming(
            local_address=self.wallet_address, unconfirmed=True
        )

        if incoming_payment == []:
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

        if len(incoming_payment) > 1:
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

        if len(incoming_payment) == 1:
            this_payment = incoming_payment.pop()
            num_confirmation_required = self.payment_method_id.num_confirmation_required
            conf_err_msg = (
                f"PaymentMethod: {self.payment_method_id.name} "
                f"Subaddress: {self.wallet_address} "
                "Status: Waiting for more confirmations "
                f"Confirmations: current {this_payment.transaction.confirmations}, "
                f"expected {num_confirmation_required} "
                "Action: none"
            )
            # TODO set transaction state to "authorized" once a monero transaction is
            #  found within the transaction pool
            # note that when the NumConfirmationsNotMe is raised any database commits
            # are lost
            if this_payment.transaction.confirmations is None:
                if num_confirmation_required > 0:
                    raise NumConfirmationsNotMet(conf_err_msg)
            else:
                if this_payment.transaction.confirmations < num_confirmation_required:
                    raise NumConfirmationsNotMet(conf_err_msg)

            transaction_amount_rounded = float(
                round(this_payment.amount, self.currency_id.decimal_places)
            )
            if self.amount == transaction_amount_rounded:
                self.pos_order_id.write({"state": "done"})
                self.write({"payment_status": "done"})
                _logger.info(
                    f"Monero payment recorded for pos order: {self.pos_order_id.id}, "
                    f"associated with subaddress: {self.wallet_address}"
                )
                # TODO handle situation where the transaction amount is not equal
