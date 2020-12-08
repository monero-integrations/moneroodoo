import odoo.tests.common as common

from controllers import controllers

class MoneroControllerTest(common.TransactionCase):
    def test_monero_transaction(self):
        self.assertEquals('test', 'test')
