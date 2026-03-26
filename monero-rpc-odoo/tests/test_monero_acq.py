from unittest.mock import patch, MagicMock

from odoo.tests import TransactionCase, tagged

from ..models.exceptions import MoneroPaymentAcquirerRPCUnauthorized
from monero.backends.jsonrpc import Unauthorized

_MODULE = "odoo.addons.monero_rpc_odoo.models.monero_acq"


@tagged("post_install", "-at_install")
class TestMoneroPaymentAcquirer(TransactionCase):

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
            "monero_rpc_config_user": "user",
            "monero_rpc_config_password": "pass",
        })

    @patch(f"{_MODULE}.JSONRPCWallet")
    def test_get_wallet_unauthorized(self, mock_rpc):
        """get_wallet() raises MoneroPaymentAcquirerRPCUnauthorized on bad credentials."""
        from monero.wallet import Wallet
        with patch.object(Wallet, "__init__", side_effect=Unauthorized):
            with self.assertRaises(MoneroPaymentAcquirerRPCUnauthorized):
                self.provider.get_wallet()

    @patch(f"{_MODULE}.http_requests.get")
    def test_update_xmr_rate_creates_rate(self, mock_get):
        """update_xmr_rate() creates a res.currency.rate record when HTTP succeeds."""
        mock_get.return_value = MagicMock(
            raise_for_status=lambda: None,
            json=lambda: {"monero": {"usd": 200.0}},
        )
        xmr = self.env["res.currency"].search([("name", "=", "XMR")], limit=1)
        if not xmr:
            xmr = self.env["res.currency"].create({"name": "XMR", "symbol": "ɱ"})

        self.provider.update_xmr_rate()

        from datetime import date
        rate_record = self.env["res.currency.rate"].search([
            ("currency_id", "=", xmr.id),
            ("name", "=", date.today()),
        ], limit=1)
        self.assertTrue(rate_record, "A currency rate record should have been created")
        self.assertAlmostEqual(rate_record.rate, 1.0 / 200.0, places=8)

    @patch(f"{_MODULE}.http_requests.get")
    def test_update_xmr_rate_http_failure(self, mock_get):
        """update_xmr_rate() returns gracefully when the HTTP request fails."""
        mock_get.side_effect = Exception("network error")
        self.provider.update_xmr_rate()  # should not raise

    @patch(f"{_MODULE}.http_requests.get")
    def test_update_xmr_rate_updates_existing(self, mock_get):
        """update_xmr_rate() updates an existing rate record instead of creating a duplicate."""
        mock_get.return_value = MagicMock(
            raise_for_status=lambda: None,
            json=lambda: {"monero": {"usd": 150.0}},
        )
        xmr = self.env["res.currency"].search([("name", "=", "XMR")], limit=1)
        if not xmr:
            xmr = self.env["res.currency"].create({"name": "XMR", "symbol": "ɱ"})

        self.provider.update_xmr_rate()
        self.provider.update_xmr_rate()

        from datetime import date
        rates = self.env["res.currency.rate"].search([
            ("currency_id", "=", xmr.id),
            ("name", "=", date.today()),
        ])
        self.assertEqual(len(rates), 1, "Should have exactly one rate record for today")

    @patch(f"{_MODULE}.http_requests.get")
    def test_update_xmr_rate_no_xmr_currency(self, mock_get):
        """update_xmr_rate() returns gracefully when XMR currency is not in Odoo."""
        mock_get.return_value = MagicMock(
            raise_for_status=lambda: None,
            json=lambda: {"monero": {"usd": 150.0}},
        )
        xmr = self.env["res.currency"].search([("name", "=", "XMR")], limit=1)
        if xmr:
            xmr.write({"active": False})
        self.provider.update_xmr_rate()  # should not raise

    def test_post_process_confirms_order(self):
        """_post_process() confirms a linked draft sale order for monero_rpc provider."""
        partner = self.env["res.partner"].create({"name": "Test Partner"})
        order = self.env["sale.order"].create({"partner_id": partner.id})
        self.assertEqual(order.state, "draft")

        tx = self.env["payment.transaction"].create({
            "provider_id": self.provider.id,
            "amount": 10.0,
            "currency_id": self.env.ref("base.USD").id,
            "partner_id": partner.id,
            "reference": "TEST-XMR-001",
        })
        tx.sale_order_ids = order
        tx._set_done()
        tx._post_process()

        self.assertEqual(order.state, "sale", "Sale order should be confirmed after _post_process")
