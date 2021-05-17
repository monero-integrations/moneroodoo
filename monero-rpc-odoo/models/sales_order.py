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
            wallet = transaction.acquirer_id.get_wallet()
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

        incoming_payment = wallet.incoming(local_address=token.name, unconfirmed=True)

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

        if len(incoming_payment) > 1:
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

        if len(incoming_payment) == 1:
            this_payment = incoming_payment.pop()

            conf_err_msg = (
                f"PaymentAcquirer: {transaction.acquirer_id.provider} "
                f"Subaddress: {token.name} "
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
            if transaction.amount == transaction_amount_rounded:
                self.write({"state": "sale"})
                transaction.write({"state": "done", "is_processed": "true"})
                _logger.info(
                    f"Monero payment recorded for sale order: {self.id}, "
                    f"associated with subaddress: {token.name}"
                )
                # TODO handle situation where the transaction amount is not equal
