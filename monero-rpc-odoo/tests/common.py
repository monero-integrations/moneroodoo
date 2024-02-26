import logging
import traceback

from odoo.addons.payment.tests.common import PaymentCommon
from odoo.tests.common import HttpCase
from ..controllers.website_sale import MoneroWebsiteSale
_logger = logging.getLogger(__name__)

class MoneroCommon(PaymentCommon):

    @classmethod
    def setUpClass(cls, chart_template_ref="l10n_de_skr03.l10n_de_chart_template"):
        _logger.info("In MomeroCommon setUpClass")
        _logger.info(cls.env)
        try:
            super().setUpClass(chart_template_ref=chart_template_ref)
        except Exception as e:
            _logger.info(e)
            _logger.warning(traceback.format_exc())
        _logger.info(cls.env)
        _logger.info(cls.env.registry)

        values = {
            'is_cryptocurrency': True,
            'type': 'xmr',
        }
        cls.monero = cls._prepare_acquirer('monero-rpc', update_values=values)
        cls.currency_xmr = cls._prepare_currency('XMR')
        cls.acquirer = cls.monero
        cls.currency = cls.currency_xmr

        cls.sale_order = cls.env['sale.order'].create({
            'partner_id': cls.env['res.partner'].create({'name': 'Test Partner'}).id,
            'note': 'Invoice after delivery',
            'payment_term_id': cls.env.ref('account.account_payment_term_end_following_month').id,
            'currency_id': cls.currency_xmr.id,
        })
        cls.website = cls.env['website'].browse(1)
        cls.WebsiteSaleController = MoneroWebsiteSale()
        cls.public_user = cls.env.ref('base.public_user')

class TestWebsiteSaleCommon(HttpCase):

    @classmethod
    def setUpClass(cls):
        super(TestWebsiteSaleCommon, cls).setUpClass()
        # Update website pricelist to ensure currency is same as env.company

        cls.website = cls.env['website'].browse(1)
        cls.WebsiteSaleController = MoneroWebsiteSale()
        cls.public_user = cls.env.ref('base.public_user')
        website = cls.env['website'].get_current_website()
        pricelist = website.get_current_pricelist()
        pricelist.write({'currency_id': cls.env.company.currency_id.id})
