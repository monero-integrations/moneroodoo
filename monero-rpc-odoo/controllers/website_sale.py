import logging

from odoo import http
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.payment.models.payment_acquirer import PaymentAcquirer
# from odoo.api.payment import acquirer
from odoo.http import request

_logger = logging.getLogger(__name__)


class MoneroWebsiteSale(WebsiteSale):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @http.route(['/shop/payment'], type='http', auth="public", website=True, sitemap=False)
    def payment(self, **post):
        """
        OVERRIDING METHOD FROM odoo/addons/website_sale/controllers/main.py
        Payment step. This page proposes several payment means based on available
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
        render_values['only_services'] = order and order.only_services or False
        acquirer: PaymentAcquirer
        for acquirer in render_values['acquirers']:
            _logger.info(f'acq_type:{type(acquirer)}')
            _logger.info(f'acquirer:{acquirer}')
            _logger.info(f'setting:{acquirer.monero_rpc_config_host}')
            _logger.info(f'acquirer:{acquirer.provider}')
            if 'monero-rpc' in acquirer.provider:
                wallet = self.env["ir.config_parameter"].get_param("monero_wallet")
                request.wallet_address = wallet.new_address()
                _logger.info('one time payment address set')

        # tokens = render_values['tokens']
        # for token in tokens:
            # TODO remove any Monero related tokens, we don't want to reuse subaddresses
            # _logger.info(f'payment_token:{token}')

        _logger.info(
            f'render_values{render_values}'
        )

        if render_values['errors']:
            render_values.pop('acquirers', '')
            render_values.pop('tokens', '')

        return request.render("website_sale.payment", render_values)
