import logging

from odoo.http import request
from odoo import http
from odoo.exceptions import ValidationError

from monero.wallet import Wallet

from monero.backends.jsonrpc import Unauthorized
from requests.exceptions import SSLError
from odoo.addons.queue_job.exception import RetryableJobError


class MoneroPaymentMethodRPCUnauthorized(Unauthorized):
    pass


class MoneroPaymentMethodRPCSSLError(SSLError):
    pass


class NoTXFound(RetryableJobError):
    pass


class NumConfirmationsNotMet(RetryableJobError):
    pass


class MoneroAddressReuse(Exception):
    pass


_logger = logging.getLogger(__name__)


class MoneroController(http.Controller):
    @http.route(
        "/pos/monero/get_address",
        type="json",
        auth="public",
        website=True,
        methods=["POST"],
    )
    def get_address(self, **kwargs):
        """
        Function retrieves a Monero subaddress that will be used on the client side
        Client side will display a qr code
        Client side will pass subaddress via field "wallet_address" when
        pos.order.create_from_ui is called
        :param kwargs: payment_method_id
        :return: wallet_address
        """

        payment_method = (
            request.env["pos.payment.method"]
            .sudo()
            .browse(int(kwargs.get("payment_method_id")))
        )

        if payment_method is not None:
            try:
                wallet: Wallet = payment_method.get_wallet()
            except MoneroPaymentMethodRPCUnauthorized:
                _logger.error(
                    "USER IMPACT: Monero POS Payment Method "
                    "can't authenticate with RPC "
                    "due to user name or password"
                )
                raise ValidationError(
                    "Current technical issues "
                    "prevent Monero from being accepted, "
                    "choose another payment method"
                )
            except MoneroPaymentMethodRPCSSLError:
                _logger.error(
                    "USER IMPACT: Monero POS Payment Method "
                    "experienced an SSL Error with RPC"
                )
                raise ValidationError(
                    "Current technical issues "
                    "prevent Monero from being accepted, "
                    "choose another payment method"
                )
            except Exception as e:
                _logger.error(
                    f"USER IMPACT: Monero POS Payment Method "
                    f"experienced an Error with RPC: {e.__class__.__name__}"
                )
                raise ValidationError(
                    "Current technical issues "
                    "prevent Monero from being accepted, "
                    "choose another payment method"
                )

            res = {
                "wallet_address": wallet.new_address()[0],
            }
        else:
            _logger.error(
                "USER IMPACT: Monero POS Payment Method"
                "experienced an Error with payment method: Not Found"
            )
            raise ValidationError(
                "Current technical issues "
                "prevent Monero from being accepted, "
                "choose another payment method"
            )

        return res
