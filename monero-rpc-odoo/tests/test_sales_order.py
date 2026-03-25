from unittest.mock import patch, MagicMock

from odoo.tests import tagged
from odoo.addons.sale.tests.common import TestSaleCommon

from ..models.exceptions import NoTXFound, NumConfirmationsNotMet

# 1 XMR = 1_000_000_000_000 piconero
PICONERO = 1_000_000_000_000


def _make_rpc_response(subaddress, balance=0, unlocked_balance=0):
    """Helper: build a fake get_balance JSON-RPC response."""
    per_subaddress = []
    if subaddress:
        per_subaddress.append({
            "address": subaddress,
            "balance": balance,
            "unlocked_balance": unlocked_balance,
        })
    mock_resp = MagicMock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json.return_value = {"result": {"per_subaddress": per_subaddress}}
    return mock_resp


@tagged("post_install", "-at_install")
class TestMoneroSalesOrder(TestSaleCommon):

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)

        cls.partner = cls.env["res.partner"].create({
            "name": "XMR Buyer",
            "email": "buyer@example.com",
            "country_id": 1,
        })
        cls.provider = cls.env["payment.provider"].create({
            "name": "Monero RPC",
            "code": "monero_rpc",
            "journal_id": cls.env["account.journal"].search(
                [("type", "=", "bank")], limit=1
            ).id,
            "rpc_protocol": "http",
            "monero_rpc_config_host": "127.0.0.1",
            "monero_rpc_config_port": "18082",
        })

    def _make_order_and_tx(self, subaddress, xmr_amount=1.0):
        """Create a minimal sale order + pending payment transaction."""
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        tx = self.env["payment.transaction"].create({
            "provider_id": self.provider.id,
            "amount": xmr_amount,
            "currency_id": self.env.ref("base.USD").id,
            "partner_id": self.partner.id,
            "reference": f"TEST-{subaddress[:8]}",
            "provider_reference": subaddress,
            "monero_amount_xmr": xmr_amount,
        })
        tx.sale_order_ids = order
        return order, tx

    @patch("odoo.addons.monero-rpc-odoo.models.sales_order.http_requests.post")
    def test_payment_confirmed(self, mock_post):
        """Happy path: sufficient balance → transaction done, order confirmed."""
        subaddress = "TestSubAddr1"
        xmr_amount = 1.0
        balance = int(xmr_amount * PICONERO)
        mock_post.return_value = _make_rpc_response(subaddress, balance=balance, unlocked_balance=balance)

        order, tx = self._make_order_and_tx(subaddress, xmr_amount)
        order.process_transaction(tx, num_confirmation_required=0)

        self.assertEqual(tx.state, "done")
        self.assertEqual(order.state, "sale")

    @patch("odoo.addons.monero-rpc-odoo.models.sales_order.http_requests.post")
    def test_no_tx_found(self, mock_post):
        """Subaddress absent from RPC response → raises NoTXFound."""
        mock_post.return_value = _make_rpc_response(None)  # empty per_subaddress

        order, tx = self._make_order_and_tx("MissingAddr1")
        with self.assertRaises(NoTXFound):
            order.process_transaction(tx, num_confirmation_required=0)

    @patch("odoo.addons.monero-rpc-odoo.models.sales_order.http_requests.post")
    def test_confirmations_not_met(self, mock_post):
        """unlocked_balance < balance with confirmations required → raises NumConfirmationsNotMet."""
        subaddress = "TestSubAddr2"
        xmr_amount = 1.0
        balance = int(xmr_amount * PICONERO)
        # unlocked_balance is 0 — funds not yet confirmed
        mock_post.return_value = _make_rpc_response(subaddress, balance=balance, unlocked_balance=0)

        order, tx = self._make_order_and_tx(subaddress, xmr_amount)
        with self.assertRaises(NumConfirmationsNotMet):
            order.process_transaction(tx, num_confirmation_required=3)

    def test_already_done_returns_early(self):
        """process_transaction() is a no-op when transaction is already done."""
        order, tx = self._make_order_and_tx("DoneAddr1", xmr_amount=1.0)
        tx._set_done()
        # Should return without raising or changing anything
        order.process_transaction(tx, num_confirmation_required=0)
        self.assertEqual(tx.state, "done")

    @patch("odoo.addons.monero-rpc-odoo.models.sales_order.http_requests.post")
    def test_zeroconf_ignores_unlocked(self, mock_post):
        """0-conf: balance present but unlocked=0 → still confirms (no confirmation wait)."""
        subaddress = "ZeroConfAddr1"
        xmr_amount = 1.0
        balance = int(xmr_amount * PICONERO)
        # unlocked_balance=0 but num_confirmation_required=0 → should confirm
        mock_post.return_value = _make_rpc_response(subaddress, balance=balance, unlocked_balance=0)

        order, tx = self._make_order_and_tx(subaddress, xmr_amount)
        order.process_transaction(tx, num_confirmation_required=0)

        self.assertEqual(tx.state, "done")
        self.assertEqual(order.state, "sale")

    @patch("odoo.addons.monero-rpc-odoo.models.sales_order.http_requests.post")
    def test_underpayment(self, mock_post):
        """Received less than expected → order NOT confirmed, transaction stays pending."""
        subaddress = "TestSubAddr3"
        xmr_amount = 2.0
        received = int(0.5 * PICONERO)  # only half paid
        mock_post.return_value = _make_rpc_response(subaddress, balance=received, unlocked_balance=received)

        order, tx = self._make_order_and_tx(subaddress, xmr_amount)
        order.process_transaction(tx, num_confirmation_required=0)

        self.assertNotEqual(tx.state, "done", "Underpayment should not confirm the transaction")
        self.assertNotEqual(order.state, "sale", "Underpayment should not confirm the order")
