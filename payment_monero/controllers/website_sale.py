# -*- coding: utf-8 -*-

import logging

from typing import override

from odoo import http
from odoo.http import request
from odoo.exceptions import ValidationError
from odoo.addons.website_sale.controllers.main import WebsiteSale

from monero import MoneroWallet

_logger = logging.getLogger(__name__)


class MoneroWebsiteSale(WebsiteSale):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @http.route(
        ["/shop/payment"], type="http", auth="public", website=True, sitemap=False
    )
    @override
    def shop_payment(self, **post):
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
        _logger.info("In Payment")
        order = request.website.sale_get_order()
        redirection = self.checkout_redirection(order)
        if redirection:
            return redirection

        render_values = self._get_shop_payment_values(order, **post)
        render_values["only_services"] = order and order.only_services or False

        for acquirer in render_values["acquirers"]:
            if "monero" in acquirer.provider:
                if acquirer.is_wallet_loaded():
                    # wallet already loaded
                    break

                wallet: MoneroWallet | None = None
                try:
                    wallet = acquirer.get_wallet()
                except Exception as e:
                    _logger.error(
                        f"USER IMPACT: Monero Payment Acquirer "
                        f"experienced an Error with wallet: {str(e)}"
                    )
                    raise ValidationError(
                        "Current technical issues "
                        "prevent Monero from being accepted, "
                        "choose another payment method"
                    )

                if wallet is None:
                    raise ValidationError(
                        "Could not get a monero wallet to receive payment order"
                    )

                _logger.info(f"Monero wallet loaded, restore height {wallet.get_restore_height()}")

        if render_values["errors"]:
            render_values.pop("acquirers", "")
            render_values.pop("tokens", "")

        return request.render("website_sale.payment", render_values)
