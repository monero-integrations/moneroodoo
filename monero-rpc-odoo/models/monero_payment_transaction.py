# -*- coding: utf-8 -*-

from __future__ import annotations

from typing_extensions import override

import logging

from odoo import api, _
from odoo.models import fields
from odoo.addons.payment.models import payment_transaction, payment_token
from odoo.exceptions import ValidationError
from odoo.http import request

from monero import MoneroSubaddress, MoneroUtils

from ..models.exceptions import NoTXFound, NumConfirmationsNotMet, MoneroAddressReuse
from ..models.exceptions import MoneroPaymentAcquirerRPCUnauthorized
from ..models.exceptions import MoneroPaymentAcquirerRPCSSLError

from ..controllers.monero_controller import MoneroController

from .monero_payment_acquirer import MoneroPaymentAcquirer
from ..utils import MoneroKrakenRateConverter

_logger = logging.getLogger(__name__)


class MoneroPaymentTransaction(payment_transaction.PaymentTransaction):
    _inherit = 'payment.transaction'
    _provider_key = 'monero-rpc'

    # missing
    id: str

    # override
    acquirer_id: MoneroPaymentAcquirer

    #region Odoo Fields

    fully_paid = fields.Boolean(
        string="Fully Paid", help="Indicates if transaction is fully paid",
        default=False
    )

    currency_monero_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env['res.currency'].search([('name', '=', 'XMR')], limit=1).id
    )

    exchange_rate = fields.Monetary(
        string="Exchange Rate", currency_field='currency_id', readonly=True, required=True)

    amount_xmr = fields.Monetary(
        string="Amount XMR", currency_field='currency_monero_id', readonly=True, required=True)

    amount_remaining_xmr = fields.Monetary(
        string="Amount remaining to be paid XMR", currency_field='currency_monero_id', readonly=True, required=True)

    amount_paid_xmr = fields.Monetary(
        string="Amount paid XMR", currency_field='currency_monero_id', readonly=False, required=False,
        default=0
    )

    confirmations_required = fields.Integer(
        string="Number of network confirmations required", default = 0
    )

    #endregion

    #region Override Methods

    @override
    def _get_specific_rendering_values(self, processing_values: dict) -> dict:
        """ Override of payment to return Transfer-specific rendering values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic and specific processing values of the transaction
        :return: The dict of acquirer-specific processing values
        :rtype: dict
        """

        _logger.warning("In Monero Transaction _get_specific_rendering_values")
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider != self._provider_key:
            return res
        #         wallet = self.acquirer_id.get_wallet()
        return {
            'api_url': MoneroController._accept_url,
            'reference': self.reference,
            #             'wallet_address': wallet.new_address()[0],
        }

    @override
    def _process_feedback_data(self, data: dict, order_id=None) -> None:
        """ Override of payment to process the transaction based on transfer data.

        Note: self.ensure_one()

        :param dict data: The transfer feedback data
        :return: None
        """
        _logger.warning("In _process_feedback_data")
        _logger.warning("IDs: {}".format(self._ids))
        _logger.warning("References: {}".format(self.reference))
        super()._process_feedback_data(data)
        if self.provider != self._provider_key:
            return
        _logger.warning("data: {}".format(data))
        _logger.info(
            "validated transfer payment for tx with reference %s: set as pending", self.reference
        )
        self._set_pending()
        token = self._monero_tokenize_from_feedback_data(data)
        self._set_listener(token=token)

    @api.model
    @override
    def _get_tx_from_feedback_data(self, provider: str, data: dict) -> MoneroPaymentTransaction:
        """ Override of payment to find the transaction based on transfer data.

        :param str provider: The provider of the acquirer that handled the transaction
        :param dict data: The transfer feedback data
        :return: The transaction if found
        :rtype: recordset of `payment.transaction`
        :raise: ValidationError if the data match no transaction
        """
        tx = super()._get_tx_from_feedback_data(provider, data)
        if provider != self._provider_key:
            return tx

        reference = data.get('reference')
        tx = self.search([('reference', '=', reference), ('provider', '=', self._provider_key)])
        _logger.warning(tx)

        if not isinstance(tx, MoneroPaymentTransaction):
            raise ValidationError(
                "Monero Transaction: " + _("No transaction found matching reference %s.", reference)
            )
        return tx

    @api.model
    @override
    def create(self, vals):
        if 'exchange_rate' not in vals:
            try:
                vals['exchange_rate'] = self.get_current_exchange_rate()
            except Exception as e:
                raise ValueError(f"Could not get exchange rate: {e}")
        if 'amount_xmr' not in vals:
            try:
                vals['amount_xmr'] = self.usd_to_xmr(vals['amount'])
            except Exception as e:
                raise ValueError(f"Could not convert usd to xmr: {e}")
        
        if 'amount_paid_xmr' not in vals:
            vals['amount_paid_xmr'] = 0

        if 'amount_remaining_xmr' not in vals:
            vals['amount_remaining_xmr'] = vals['amount_xmr']

        return super().create(vals)

    #endregion

    #region Convenience Methods

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

    def get_decimal_places(self) -> float:
        return float(self.currency_id.decimal_places) # type: ignore

    def get_current_exchange_rate(self) -> float:
        converter = MoneroKrakenRateConverter()
        return converter.get_exchange_rate()

    def usd_to_xmr(self, usd: float) -> float:
        converter = MoneroKrakenRateConverter()
        return converter.usd_to_xmr(usd)

    #endregion

    #region Private Methods

    def _cron_check_status(self):
        """
            Cron to send invoice that where not ready to be send directly after posting
        """
        self.env["sale.order"]

    def _set_listener(self, token: payment_token.PaymentToken | None = None) -> None:

        # set queue channel and max_retries settings
        # for queue depending on num conf settings
        num_conf_req = self.acquirer_id.get_num_confirmations_required()
        if num_conf_req == 0:
            queue_channel = "monero_zeroconf_processing"
            queue_max_retries = 44
        else:
            queue_channel = "monero_secure_processing"
            queue_max_retries = num_conf_req * 25

        # Add payment token and sale order to transaction processing queue
        _logger.warning("_set_listener(): request: {}".format(request))
        _logger.warning("_set_listener(): session: {}".format(request.session))
        last_order_id = request.session['sale_last_order_id']
        _logger.warning(f"_set_listener(): last_order_id: {last_order_id}")
        order = request.env['sale.order'].sudo().browse(last_order_id).exists()
        # order = request.website.sale_get_order()
        _logger.warning("order: {}".format(order))

        order.with_delay(
            channel=queue_channel, max_retries=queue_max_retries
        ).update_transaction(transaction=self, token=token, num_confirmation_required=num_conf_req)

        order.with_delay(
            channel=queue_channel, max_retries=queue_max_retries
        ).process_transaction(transaction=self, token=token, num_confirmation_required=num_conf_req)

    def _monero_tokenize_from_feedback_data(self, data: dict) -> payment_token.PaymentToken:
        """ Create a token from feedback data.

            :param dict data: The feedback data sent by the provider
            :return: Token
            """
        _logger.warning("In tokenize")
        wallet_sub_address: MoneroSubaddress = self.acquirer_id.create_subaddress()
        _logger.warning("wallet_sub_address: {}".format(wallet_sub_address))
        _logger.warning("acquirer_id: {}".format(self.acquirer_id))
        #token_name = wallet_sub_address.__repr__()
        token_name = wallet_sub_address.address
        partner_id = self.partner_id.id # type: ignore
        token: payment_token.PaymentToken = self.env['payment.token'].create({
            'acquirer_ref': self.reference,
            'acquirer_id': self.acquirer_id.id,
            'name': token_name,  # Already padded with 'X's
            'partner_id': partner_id,
            'verified': True,  # The payment is authorized, so the payment method is valid
            'active': False, # The payment shall only be used once
        })
        self.write({
            'token_id': token.id,
            'tokenize': False,
        })
        _logger.info(
            "created token with id %s for partner with id %s", token.id, partner_id
        )

        return token

    #endregion

    #region Public Methods

    @api.model
    def process_transaction(self, token: payment_token.PaymentToken, num_confirmation_required: int) -> str | None:
        _logger.warning("-------CHECKPOINT PROCESS TRANSACTION 2")

        try:
            wallet = self.acquirer_id.get_wallet()
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

        address: str = str(token.name)
        incoming_payment = self.acquirer_id.get_incoming_unconfirmed_transfers(address)
        # TODO: What do we do if we have multiple orders at the same time?
        _logger.warning("Incoming Payments: {}".format(incoming_payment))

        if incoming_payment == []:
            job = (
                self.env["queue.job"]
                .sudo()
                .search([("uuid", "=", self.env.context.get("job_uuid"))])
            )
            _logger.info(job.max_retries)
            _logger.info(job.retry)
            if job.retry == job.max_retries - 1:
                self._set_canceled(state_message="Cancelling due to too many retries")
                log_msg = (
                    f"PaymentAcquirer: {self.acquirer_id.provider} "
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
                    f"PaymentAcquirer: {self.acquirer_id.provider} "
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
                f"PaymentAcquirer: {self.acquirer_id.provider} "
                f"Subaddress: {token.name} "
                "Status: Address reuse found. "
                "The end user most likely sent "
                "multiple transactions for a single order. "
                "Action: Reconcile transactions manually"
            )

        if len(incoming_payment) == 1:
            this_payment = incoming_payment.pop()

            conf_err_msg = (
                f"PaymentAcquirer: {self.acquirer_id.provider} "
                f"Subaddress: {token.name} "
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
            
            # transfer amount in atomic units
            transfer_amount = this_payment.amount if this_payment.amount is not None else 0
            # amount to pay in atomic units
            amount_to_pay = self.get_amount_xmr_atomic_units()
            payment_suffices = transfer_amount >= amount_to_pay

            _logger.info(f"Transfer amount: {transfer_amount}, amount to pay: {amount_to_pay}, payment suffices: {payment_suffices}")

            if payment_suffices:
                self._set_done()
                _logger.info(
                    f"Monero payment recorded for sale order: {self.id}, "
                    f"associated with subaddress: {token.name}"
                )

                # TODO handle situation where the transaction amount is not equal
            else:
                _logger.warning("transaction amount was not equal")

    #endregion


def build_token_name(payment_details_short: str | None = None, final_length: int = 16) -> str:
    """ Pad plain payment details with leading X's to build a token name of the desired length.

    :param str payment_details_short: The plain part of the payment details (usually last 4 digits)
    :param int final_length: The desired final length of the token name (16 for a bank card)
    :return: The padded token name
    :rtype: str
    """
    payment_details_short = payment_details_short or '????'
    return f"{'X' * (final_length - len(payment_details_short))}{payment_details_short}"
