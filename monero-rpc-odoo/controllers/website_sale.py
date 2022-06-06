import logging

from odoo import http
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.exceptions import ValidationError, UserError

from ..models.exceptions import MoneroPaymentAcquirerRPCUnauthorized
from ..models.exceptions import MoneroPaymentAcquirerRPCSSLError
from odoo.http import request

import requests

from urllib3 import exceptions
from monero import exceptions
from monero.backends.jsonrpc import JSONRPCDaemon, RPCError

_logger = logging.getLogger(__name__)


class MoneroWebsiteSale(WebsiteSale):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @http.route(
        ["/shop/payment"], type="http", auth="public", website=True, sitemap=False
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

        for acquirer in render_values["acquirers"]:
            if "monero-rpc" in acquirer.provider:
                wallet = None
                try:
                    wallet = acquirer.get_wallet()
                    request.wallet_address = wallet.new_address()[0]
                    _logger.debug("new monero payment subaddress generated")
                except MoneroPaymentAcquirerRPCUnauthorized:
                    _logger.error(
                        "USER IMPACT: Monero Payment Acquirer "
                        "can't authenticate with RPC "
                        "due to user name or password"
                    )
                    raise ValidationError(
                        "Current technical issues "
                        "prevent Monero from being accepted, "
                        "choose another payment method"
                    )
                except MoneroPaymentAcquirerRPCSSLError:
                    _logger.error(
                        "USER IMPACT: Monero Payment Acquirer "
                        "experienced an SSL Error with RPC"
                    )
                    raise ValidationError(
                        "Current technical issues "
                        "prevent Monero from being accepted, "
                        "choose another payment method"
                    )
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                    _logger.error('Monero RPC connection issue: %s', e)
                except (urllib3.exceptions.HTTPError, urllib3.exceptions.NewConnectionError, urllib3.exceptions.MaxRetryError) as e:
                    _logger.error('connection error urllib3: %s', e)
                    raise UserError('urllib3 connection error.')
                except Exception as e:
                    _logger.error(
                        "USER IMPACT: Monero Payment Acquirer "
                        "experienced an Error with RPC: {e.__class__.__name__} %s", e
                    )
                    # raise ValidationError(
                    #    "Current technical issues "
                    #    "prevent Monero from being accepted, "
                    #    "choose another payment method"
                    #)
                    return None

        if render_values["errors"]:
            render_values.pop("acquirers", "")
            render_values.pop("tokens", "")

        return request.render("website_sale.payment", render_values)
