import odoo.tests.common as common


class MoneroPaymentAcquirerTest(common.TransactionCase):
    def test_get_providers(self):
        self.assertEquals('test', 'test')
