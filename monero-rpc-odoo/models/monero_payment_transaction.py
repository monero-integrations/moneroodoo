import logging

from odoo import models, api, _
from odoo.exceptions import ValidationError
from odoo.http import request

from ..models.exceptions import NoTXFound, NumConfirmationsNotMet, MoneroAddressReuse
from ..models.exceptions import MoneroPaymentAcquirerRPCUnauthorized
from ..models.exceptions import MoneroPaymentAcquirerRPCSSLError

from monero.address import SubAddress

from ..controllers.monero_controller import MoneroController

_logger = logging.getLogger(__name__)


class MoneroPaymentTransaction(models.Model):
    _inherit = 'payment.transaction'
    _provider_key = 'monero-rpc'

    def _cron_check_status(self):
        """
            Cron to send invoice that where not ready to be send directly after posting
        """
        self.env["sale.order"]

    def _get_specific_rendering_values(self, processing_values):
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

    def _process_feedback_data(self, data, order_id=None):
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

    def _set_listener(self, token=None):

        # set queue channel and max_retries settings
        # for queue depending on num conf settings
        num_conf_req = int(self.acquirer_id.num_confirmation_required)
        if num_conf_req == 0:
            queue_channel = "monero_zeroconf_processing"
            queue_max_retries = 44
        else:
            queue_channel = "monero_secure_processing"
            queue_max_retries = num_conf_req * 25

        # Add payment token and sale order to transaction processing queue
        # last_order_id = request.session['sale_last_order_id']
        # order = request.env['sale.order'].sudo().browse(last_order_id).exists()
        order = request.website.sale_get_order()
        _logger.warning("order: {}".format(order))
        order.with_delay(
            channel=queue_channel, max_retries=queue_max_retries
        ).process_transaction(self, token, num_conf_req)

    def _monero_tokenize_from_feedback_data(self, data):
        """ Create a token from feedback data.

            :param dict data: The feedback data sent by the provider
            :return: None
            """
        _logger.warning("In tokenize")
        wallet_sub_address = SubAddress(self.acquirer_id.get_wallet().new_address()[0])
        _logger.warning("wallet_sub_address: {}".format(wallet_sub_address))
        _logger.warning("acquirer_id: {}".format(self.acquirer_id))
        token_name = wallet_sub_address.__repr__()

        token = self.env['payment.token'].create({
            'acquirer_ref': self.reference,
            'acquirer_id': self.acquirer_id.id,
            'name': token_name,  # Already padded with 'X's
            'partner_id': self.partner_id.id,
            'verified': True,  # The payment is authorized, so the payment method is valid
            'active': False, # The payment shall only be used once
        })
        self.write({
            'token_id': token.id,
            'tokenize': False,
        })
        _logger.info(
            "created token with id %s for partner with id %s", token.id, self.partner_id.id
        )

        return token

    @api.model
    def _get_tx_from_feedback_data(self, provider, data):
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
        if not tx:
            raise ValidationError(
                "Monero Transaction: " + _("No transaction found matching reference %s.", reference)
            )
        return tx

    def process_transaction(self, token, num_confirmation_required):
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

        incoming_payment = wallet.incoming(local_address=token.name, unconfirmed=True)
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
                self._set_cancelled(state_message="Cancelling due to too many retries")
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

            # need to convert, because this_payment.amount is of type decimal.Decimal...
            if abs(float(this_payment.amount) - self.amount) <= 10 ** (- float(self.currency_id.decimal_places)):
                self._set_done()
                #transaction.write({"state": "done", "is_processed": "true"})
                _logger.info(
                    f"Monero payment recorded for sale order: {self.id}, "
                    f"associated with subaddress: {token.name}"
                )

                # TODO handle situation where the transaction amount is not equal
            else:
                _logger.warning("transaction amount was not equal")


def build_token_name(payment_details_short=None, final_length=16):
    """ Pad plain payment details with leading X's to build a token name of the desired length.

    :param str payment_details_short: The plain part of the payment details (usually last 4 digits)
    :param int final_length: The desired final length of the token name (16 for a bank card)
    :return: The padded token name
    :rtype: str
    """
    payment_details_short = payment_details_short or '????'
    return f"{'X' * (final_length - len(payment_details_short))}{payment_details_short}"
