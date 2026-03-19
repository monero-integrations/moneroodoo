import logging

from odoo import models

from ..models.exceptions import NoTXFound, NumConfirmationsNotMet, MoneroAddressReuse
from ..models.exceptions import MoneroPaymentAcquirerRPCUnauthorized
from ..models.exceptions import MoneroPaymentAcquirerRPCSSLError

_logger = logging.getLogger(__name__)


class MoneroSalesOrder(models.Model):
    _inherit = "sale.order"

    def process_transaction(self, transaction, token, num_confirmation_required):
        try:
            wallet = transaction.provider_id.get_wallet()
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
                f"experienced an Error with RPC: {e.__class__.__name__}"
            )

        incoming_payment = wallet.incoming(local_address=token.provider_ref, unconfirmed=True)

        if incoming_payment == []:
            # Get the current cron job from context
            cron_id = self.env.context.get('cron_id')
            if cron_id:
                cron = self.env['ir.cron'].browse(cron_id)
                # Check if we're approaching the failure limit (default is 5 before deactivation)
                if cron.failure_count >= 4:  # Cancel on the 4th failure (before deactivation)
                    self.write({"state": "cancel", "is_expired": "true"})
                    log_msg = (
                        f"PaymentProvider: {transaction.provider_id.code} "
                        f"Subaddress: {token.provider_ref} "
                        "Status: No transaction found. Too much time has passed, "
                        "customer has most likely not sent payment. "
                        f"Cancelling order # {self.id}. "
                        f"Action: Nothing"
                    )
                    _logger.warning(log_msg)
                    return log_msg

            # If not the last retry, raise exception for cron to handle retry
            exception_msg = (
                f"PaymentProvider: {transaction.provider_id.code} "
                f"Subaddress: {token.provider_ref} "
                "Status: No transaction found. "
                "TX probably hasn't been added to a block or mem-pool yet. "
                "This is fine. "
                f"Another job will execute. Action: Nothing"
            )
            raise NoTXFound(exception_msg)

        if len(incoming_payment) > 1:
            # TODO custom logic if the end user sends
            #  multiple transactions for one order
            raise MoneroAddressReuse(
                f"PaymentProvider: {transaction.provider_id.code} "
                f"Subaddress: {token.provider_ref} "
                "Status: Address reuse found. "
                "The end user most likely sent "
                "multiple transactions for a single order. "
                "Action: Reconcile transactions manually"
            )

        if len(incoming_payment) == 1:
            this_payment = incoming_payment.pop()

            conf_err_msg = (
                f"PaymentProvider: {transaction.provider_id.code} "
                f"Subaddress: {token.provider_ref} "
                "Status: Waiting for more confirmations "
                f"Confirmations: current {this_payment.transaction.confirmations}, "
                f"expected {num_confirmation_required} "
                "Action: none"
            )
            if this_payment.transaction.confirmations is None:
                if num_confirmation_required > 0:
                    raise NumConfirmationsNotMet(conf_err_msg)
            else:
                if this_payment.transaction.confirmations < num_confirmation_required:
                    raise NumConfirmationsNotMet(conf_err_msg)

            transaction_amount_rounded = float(
                round(this_payment.amount, self.currency_id.decimal_places)
            )
            if transaction.amount == transaction_amount_rounded:
                self.write({"state": "sale"})
                transaction._set_done()
                _logger.info(
                    f"Monero payment recorded for sale order: {self.id}, "
                    f"associated with subaddress: {token.provider_ref}"
                )
            # TODO handle situation where the transaction amount is not equal
