import logging

from odoo.tests import tagged
from odoo.addons.website.tools import MockRequest



from .common import MoneroCommon
from ..controllers.monero_controller import MoneroController

_logger = logging.getLogger(__name__)


@tagged('post_install', '-at_install')
class MoneroForm(MoneroCommon):
    def test_redirect_form_values(self):
        tx = self.create_transaction(flow='redirect')
        processing_values = tx._get_processing_values()
        _logger.info(processing_values["amount"])
        _logger.info(processing_values["reference"])
        self.assertEqual(processing_values['amount'], 1111.11, "Amounts do not equal")

    def test_feedback_processing(self):
        self.acquirer.monero_rpc_config_port = 18083
        self.acquirer.monero_rpc_config_user = "user"
        self.acquirer.monero_rpc_config_password = "password"
        tx = self.create_transaction(flow='redirect')
        _logger.info(tx.reference)
        _logger.info(tx.provider)
        with MockRequest(self.env, website=self.website.with_user(self.public_user)):
        #    env = self.env(test_cursor)
            self.env['payment.transaction']._handle_feedback_data('monero-rpc', {"reference": "Test Transaction"})

    def test_sale_order_status(self):
        from ..models import sales_order

        #sale_order = self.env['sale.order'].create({
        #    'amount_total': 123.41,
        #    'partner_id': 'monero-rpc',
        #})
        #sale_order.unlink()

        token = "1234556"
        num_confirmation_required = 0
        with MockRequest(self.env, website=self.website):
            sale_order = self.website.sale_get_order()
            acs = self.WebsiteSaleController._get_shop_payment_values(sale_order)["acquirers"]
            _logger.info(acs)
            acquirer = next(a for a in acs if acs.provider == "monero-rpc")
            transaction = self.env['payment.transaction'].create({
                'acquirer_id': acquirer,
            })
            sale_order.process_transaction(transaction, token, num_confirmation_required)




