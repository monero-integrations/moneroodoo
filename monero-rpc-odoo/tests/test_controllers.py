from unittest.mock import patch, MagicMock

from odoo.tests import tagged, TransactionCase
from odoo.exceptions import ValidationError

from ..models.exceptions import MoneroPaymentAcquirerRPCUnauthorized


@tagged("post_install", "-at_install")
class TestMoneroWebsiteSale(TransactionCase):

    def setUp(self):
        super().setUp()
        self.provider = self.env["payment.provider"].create({
            "name": "Monero RPC Test",
            "code": "monero_rpc",
            "journal_id": self.env["account.journal"].search(
                [("type", "=", "bank")], limit=1
            ).id,
            "rpc_protocol": "http",
            "monero_rpc_config_host": "127.0.0.1",
            "monero_rpc_config_port": "18082",
        })

    @patch("odoo.addons.monero-rpc-odoo.controllers.website_sale.WebsiteSale._get_shop_payment_values")
    def test_rpc_unauthorized_raises_validation_error(self, mock_super):
        """_get_shop_payment_values raises ValidationError when RPC auth fails."""
        mock_super.return_value = {"payment_providers": [self.provider]}

        self.provider.get_wallet = MagicMock(side_effect=MoneroPaymentAcquirerRPCUnauthorized)

        from ..controllers.website_sale import MoneroWebsiteSale
        controller = MoneroWebsiteSale()

        with self.assertRaises(ValidationError):
            controller._get_shop_payment_values(order=MagicMock())

    @patch("odoo.addons.monero-rpc-odoo.controllers.website_sale.WebsiteSale._get_shop_payment_values")
    def test_no_monero_provider_passes_through(self, mock_super):
        """No monero provider in list → render values returned unchanged, no wallet call."""
        other_provider = MagicMock()
        other_provider.code = "paypal"
        mock_super.return_value = {"payment_providers": [other_provider]}

        from ..controllers.website_sale import MoneroWebsiteSale
        controller = MoneroWebsiteSale()

        result = controller._get_shop_payment_values(order=MagicMock())

        self.assertIn("payment_providers", result)
        other_provider.get_wallet.assert_not_called()
