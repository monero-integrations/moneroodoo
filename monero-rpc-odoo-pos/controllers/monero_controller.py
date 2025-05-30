import logging

from odoo.http import request
from odoo import http
from odoo.exceptions import ValidationError

from monero import MoneroSubaddress

_logger = logging.getLogger(__name__)


class MoneroController(http.Controller):
    @http.route(
        "/pos/monero/get_address", type="json", auth="public", website=True, methods=["POST"]
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
            .browse(int(kwargs.get("payment_method_id"))) # type: ignore
        )

        if payment_method is not None:
            try:
                subaddress: MoneroSubaddress = payment_method.create_subaddress()
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
                "wallet_address": subaddress.address
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
