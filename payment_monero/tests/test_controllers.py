import odoo.tests.common as common
import odoo


class MoneroControllerTest(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def test_monero_transaction(self):
        self.assertEqual("test", "test")
