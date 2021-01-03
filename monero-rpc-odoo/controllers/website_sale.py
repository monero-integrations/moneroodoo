import logging

from odoo import http
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.exceptions import ValidationError
# from odoo.api.payment import acquirer
from ..models.monero_acq import MoneroPaymentAcquirer
from ..models.exceptions import MoneroPaymentAcquirerRPCUnauthorized
from ..models.exceptions import MoneroPaymentAcquirerRPCSSLError
from monero.wallet import Wallet
from odoo.http import request

_logger = logging.getLogger(__name__)


class MoneroWebsiteSale(WebsiteSale):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @http.route(
        ["/shop/payment"], type="http", auth="public",
        website=True, sitemap=False
    )
    def payment(self, **post):
        """
        OVERRIDING METHOD FROM
        odoo/addons/website_sale/controllers/main.py
        Payment step. This page proposes several
        payment means based on available
        payment.acquirer. State at this point :
         - a draft sales order with lines; otherwise, clean context / session and
           back to the shop
         - no transaction in context / session, or only a draft one, if the customer
           did go to a payment.acquirer website but closed the tab without
           paying / canceling
        """
        order = request.website.sale_get_order()
        redirection = self.checkout_redirection(order)
        if redirection:
            return redirection

        render_values = self._get_shop_payment_values(order, **post)
        render_values["only_services"] = order and order.only_services or False
        acquirer: PaymentAcquirer
        for acquirer in render_values["acquirers"]:
            if "monero-rpc" in acquirer.provider:
                wallet = None
                try:
                    wallet = acquirer.get_wallet()
                except MoneroPaymentAcquirerRPCUnauthorized:
                    _logger.error("USER IMPACT: Monero Payment Acquirer "
                                  "can't authenticate with RPC "
                                  "due to user name or password")
                    raise ValidationError("Current technical issues "
                                          "prevent Monero from being accepted, "
                                          "choose another payment method")
                except MoneroPaymentAcquirerRPCSSLError:
                    _logger.error("USER IMPACT: Monero Payment Acquirer "
                                  "experienced an SSL Error with RPC")
                    raise ValidationError("Current technical issues "
                                          "prevent Monero from being accepted, "
                                          "choose another payment method")
                except Exception as e:
                    _logger.error(f"USER IMPACT: Monero Payment Acquirer "
                                  f"experienced an Error with RPC: {e.__class__.__name__}")
                    raise ValidationError("Current technical issues"
                                          "prevent Monero from being accepted, "
                                          "choose another payment method")

                request.wallet_address = wallet.new_address()[0]
                _logger.info("new monero payment subaddress generated")

        # tokens = render_values['tokens']
        # for token in tokens:
        # TODO remove any Monero related tokens, we don't want to reuse subaddresses
        # _logger.info(f'payment_token:{token}')

        _logger.info(f"render_values{render_values}")

        if render_values["errors"]:
            render_values.pop("acquirers", "")
            render_values.pop("tokens", "")

        return request.render("website_sale.payment", render_values)
