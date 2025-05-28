# -*- coding: utf-8 -*-

import logging

from odoo import api
from odoo.addons.payment.models import payment_token
from odoo.addons.sale.models import sale_order

from monero import MoneroIncomingTransfer

from ..models.exceptions import NoTXFound, NumConfirmationsNotMet, MoneroAddressReuse
from ..models.exceptions import MoneroPaymentAcquirerRPCUnauthorized
from ..models.exceptions import MoneroPaymentAcquirerRPCSSLError

_logger = logging.getLogger(__name__)


class MoneroSalesOrder(sale_order.SaleOrder):
    _inherit = "sale.order"

    # region Missing

    id: str

    # endregion

    @api.model
    def process_transaction(self, transaction, token: payment_token.PaymentToken, num_confirmation_required: int):
        _logger.warning("-------CHECKPOINT PROCESS TRANSACTION")
        _logger.warning("self: {}".format(self))
        _logger.warning("amount total: {}".format(self.amount_total))

        transfers: list[MoneroIncomingTransfer] = []
        total_amount: int = 0
        address = ""

        try:
            address = str(token.name)
            transfers = transaction.acquirer_id.get_incoming_unconfirmed_transfers(address)

            for transfer in transfers:
                if transfer.amount is None:
                    continue
                total_amount += transfer.amount

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

        _logger.warning("Incoming Payments: {}".format(transfers))

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
