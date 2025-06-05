# -*- coding: utf-8 -*-

from __future__ import annotations

import logging

from datetime import datetime

from odoo import api, fields
from odoo.addons.payment.models import payment_token
from odoo.addons.sale.models import sale_order

from monero import MoneroUtils

from ..utils import MoneroWalletIncomingTransfers

from .exceptions import ( 
    MoneroNoTransactionFoundError, MoneroNumConfirmationsNotMetError, 
    MoneroTransactionUpdateJobError 
)

from .payment_transaction import MoneroPaymentTransaction

_logger = logging.getLogger(__name__)


class MoneroSaleOrder(sale_order.SaleOrder):

    _inherit = "sale.order"

    # region Missing

    id: str

    # endregion

    def cancel(self, transaction: MoneroPaymentTransaction) -> None:
        current_state = self.get_state()
        _logger.warning(f"--------- CANCELING ORDER, state: {current_state}")
        if current_state == "cancel":
            _logger.warning(f"-------------- ORDER ALREADY CANCELLED")
            return
        
        transaction._set_canceled('Order payment expired')
        self.action_cancel()
        self.write({"state": "cancel", "is_expired": "true"})
        _logger.warning(f"--------- CANCELED ORDER, state: {self.get_state()}")

    def get_state(self) -> str:
        return str(self.state)

    def get_date_order(self) -> datetime | None:
        if not isinstance(self.date_order, fields.Datetime):
            return None
        return self.date_order # type: ignore

    @classmethod
    def _get_address_transfers(cls, transaction: MoneroPaymentTransaction, address: str) -> MoneroWalletIncomingTransfers:
        try:
            transfers = transaction.acquirer_id.get_incoming_unconfirmed_transfers(address)

            return MoneroWalletIncomingTransfers(transfers)

        except Exception as e:
            raise Exception(
                f"Monero Processing Queue: Monero Payment Acquirer "
                f"experienced an Error with RPC: {e}"
            )

    @api.model
    def update_transaction(self, transaction: MoneroPaymentTransaction, token: payment_token.PaymentToken, num_confirmation_required: int) -> None:
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

        if not transaction.is_fully_paid() and transaction.is_expired():
            self.cancel(transaction)
            _logger.warning("-------- TRANSACTION EXPIRED")

        elif not transaction.is_fully_paid() or int(transaction.confirmations_required) > 0:
            _logger.warning("-------- CONTINUE UPDATE TRANSACTION")
            raise MoneroTransactionUpdateJobError("Continue updating...")
        else:
            _logger.warning("-------- FINISHED UPDATE TRANSACTION")

    @api.model
    def process_transaction(self, transaction: MoneroPaymentTransaction, token: payment_token.PaymentToken, num_confirmation_required: int):
        _logger.warning("------- CHECKPOINT PROCESS TRANSACTION ORDER")
        _logger.warning("------- TOTAL USD: {}".format(self.amount_total))
        _logger.warning("------- TOTAL XMR: {}".format(transaction.amount_xmr))
        _logger.warning("------- TOTAL LEFT TO PAY XMR: {}".format(transaction.amount_remaining_xmr))

        incoming_transfers = self._get_address_transfers(transaction, str(token.name))
        transfers = incoming_transfers.transfers

        _logger.warning("Incoming Payments: {}".format(len(transfers)))

        if incoming_transfers.empty:
            if not transaction.is_fully_paid() and transaction.is_expired():
                self.cancel(transaction)
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
                raise MoneroNoTransactionFoundError(exception_msg)

        else:
            conf_err_msg = (
                f"PaymentAcquirer: {transaction.acquirer_id.provider} "
                f"Subaddress: {token.name} "
                "Status: Waiting for more confirmations "
                f"Confirmations: current {incoming_transfers.num_confirmations}, "
                f"expected {num_confirmation_required} "
                "Action: none"
            )
            # TODO set transaction state to "authorized" once a monero transaction is
            #  found within the transaction pool
            # note that when the MoneroNumConfirmationsNotMetError is raised any database commits
            # are lost
            _logger.warning(f"Number of confirmations required: {num_confirmation_required}, tx confirmations: {incoming_transfers.num_confirmations}, transaction confs: {transaction.confirmations_required}")
            if incoming_transfers.num_confirmations < num_confirmation_required:
                    raise MoneroNumConfirmationsNotMetError(conf_err_msg)
            
            payment_amount = incoming_transfers.amount if incoming_transfers.amount is not None else 0
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
