import odoo.tests.common as common
from models.monero_acq import MoneroPaymentAcquirer

class MoneroPaymentAcquirerTest(common.TransactionCase):
    def test_get_providers(self):
        self.assertEquals('test', 'test')
