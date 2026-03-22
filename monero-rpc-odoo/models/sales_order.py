import logging

from odoo import models

from ..models.exceptions import NoTXFound, NumConfirmationsNotMet, MoneroAddressReuse
from ..models.exceptions import MoneroPaymentAcquirerRPCUnauthorized
from ..models.exceptions import MoneroPaymentAcquirerRPCSSLError

_logger = logging.getLogger(__name__)


class MoneroSalesOrder(models.Model):
    _inherit = "sale.order"

    def process_transaction(self, transaction, num_confirmation_required):
        """
        Poll the Monero wallet RPC for an incoming payment to the subaddress
        stored in transaction.provider_reference.

        Called by the ir.cron job set up in MoneroPaymentTransaction._get_specific_rendering_values().

        :param payment.transaction transaction: The pending Monero transaction.
        :param int num_confirmation_required: Number of confirmations required.
        """
        # The subaddress is stored in provider_reference (not in a token)
        subaddress = transaction.provider_reference

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

        incoming_payment = wallet.incoming(local_address=subaddress, unconfirmed=True)

        if incoming_payment == []:
            # Get the current cron job from context
            cron_id = self.env.context.get('cron_id')
            if cron_id:
                cron = self.env['ir.cron'].browse(cron_id)
                # Cancel after 4 failed attempts (no payment found)
                if cron.failure_count >= 4:
                    self.write({"state": "cancel", "is_expired": "true"})
                    log_msg = (
                        f"PaymentProvider: {transaction.provider_id.code} "
                        f"Subaddress: {subaddress} "
                        "Status: No transaction found. Too much time has passed, "
                        "customer has most likely not sent payment. "
                        f"Cancelling order # {self.id}. "
                        f"Action: Nothing"
                    )
                    _logger.warning(log_msg)
                    return log_msg

            # Not the last retry — raise so cron retries automatically
            exception_msg = (
                f"PaymentProvider: {transaction.provider_id.code} "
                f"Subaddress: {subaddress} "
                "Status: No transaction found. "
                "TX probably hasn't been added to a block or mem-pool yet. "
                "This is fine. "
                f"Another job will execute. Action: Nothing"
            )
            raise NoTXFound(exception_msg)

        if len(incoming_payment) > 1:
            # TODO: custom logic if the buyer sends multiple transactions for one order
            raise MoneroAddressReuse(
                f"PaymentProvider: {transaction.provider_id.code} "
                f"Subaddress: {subaddress} "
                "Status: Address reuse found. "
                "The end user most likely sent "
                "multiple transactions for a single order. "
                "Action: Reconcile transactions manually"
            )

        if len(incoming_payment) == 1:
            this_payment = incoming_payment.pop()

            conf_err_msg = (
                f"PaymentProvider: {transaction.provider_id.code} "
                f"Subaddress: {subaddress} "
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

            # Compare amounts with 12 decimal places (XMR precision)
            received = round(float(this_payment.amount), 12)
            expected = round(float(transaction.amount), 12)

            if received >= expected:
                transaction._set_done()
                transaction._post_process()
                _logger.info(
                    f"Monero payment confirmed for sale order: {self.id}, "
                    f"subaddress: {subaddress}, "
                    f"received: {received} XMR"
                )
                # Deactivate the cron — payment is done
                cron_id = self.env.context.get('cron_id')
                if cron_id:
                    self.env['ir.cron'].browse(cron_id).write({'active': False})
            else:
                _logger.warning(
                    f"Monero underpayment for order {self.id}: "
                    f"expected {expected}, received {received}"
                )
