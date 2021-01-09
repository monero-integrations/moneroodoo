# -*- coding: utf-8 -*-
import logging

from odoo import fields, models

from monero.transaction import IncomingPayment
from ..models.exceptions import NoTXFound, NumConfirmationsNotMet, MoneroAddressReuse
from ..models.exceptions import MoneroPaymentAcquirerRPCUnauthorized
from ..models.exceptions import MoneroPaymentAcquirerRPCSSLError

_logger = logging.getLogger(__name__)


class MoneroSalesOrder(models.Model):
    _inherit = "sale.order"

    is_payment_recorded = fields.Boolean(
        "Is the Payment Recorded in this ERP",
        help="Cryptocurrency transactions need to be recorded and "
             "associated with this server for order handling.",
        default=False,
    )

    def process_transaction(self, transaction, token, security_level):
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

        if security_level == 0:
            # get transaction in mem_pool
            incoming_payment = wallet.incoming(local_address=token.name, unconfirmed=True, confirmed=True)
        else:
            incoming_payment = wallet.incoming(local_address=token.name)

        if incoming_payment == []:
            job = self.env["queue.job"].sudo().search([("uuid", "=", self.env.context["job_uuid"])])
            _logger.info(job.max_retries)
            _logger.info(job.retry)
            if job.retry == job.max_retries - 1:
                self.write({"is_payment_recorded": "false",
                            "state": "cancel"})

                log_msg = f"PaymentAcquirer: {transaction.acquirer_id.provider} Subaddress: {token.name} "\
                    "Status: No transaction found. Too much time has passed, customer has most likely not sent payment. "\
                    f"Cancelling order # {self.id}. "\
                    f"Action: Nothing"
                _logger.warning(log_msg)
                return log_msg
            else:
                exception_msg = f"PaymentAcquirer: {transaction.acquirer_id.provider} Subaddress: {token.name} "\
                "Status: No transaction found. TX probably hasn't been added to a block or mem-pool yet. "\
                "This is fine. "\
                f"Another job will execute. Action: Nothing"
                raise NoTXFound(exception_msg)


        if len(incoming_payment) > 1:
            # TODO custom logic if the end user sends
            #  multiple transactions for one order
            raise MoneroAddressReuse(
                f"PaymentAcquirer: {transaction.acquirer_id.provider} Subaddress: {token.name} "
                "Status: Address reuse found. The end user most likely sent multiple transactions for a single order. "
                "Action: Reconcile transactions manually"
            )

        if len(incoming_payment) == 1:
            this_payment: IncomingPayment = incoming_payment.pop()

            transaction_amount_rounded = float(round(this_payment.amount, self.currency_id.decimal_places))

            if transaction.amount == transaction_amount_rounded:

                self.write({"is_payment_recorded": "true",
                                   "state": "sale"})
                transaction.write({"state": "done"})
                _logger.info(f"Monero payment recorded for sale order: {self.id}, associated with subaddress: {token.name}")

                # set token to inactive
                # we do not want to reuse subaddresses
                token.write({"active": "false"})
