from unittest.mock import patch, MagicMock

from odoo.tests import tagged, TransactionCase

from ..models.exceptions import NoTXFound, NumConfirmationsNotMet

_MODULE = "odoo.addons.monero_rpc_odoo.models.sales_order"

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
class TestMoneroSalesOrder(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({
            "name": "XMR Buyer",
            "email": "buyer@example.com",
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
        # Odoo 19 requires payment_method_id on payment.transaction
        cls.payment_method = cls.env["payment.method"].search(
            [("code", "=", "monero_rpc")], limit=1
        )
        if not cls.payment_method:
            cls.payment_method = cls.env["payment.method"].search([], limit=1)

    def _make_order_and_tx(self, subaddress, xmr_amount=1.0):
        """Create a minimal sale order + pending payment transaction."""
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        tx = self.env["payment.transaction"].create({
            "provider_id": self.provider.id,
            "payment_method_id": self.payment_method.id,
            "amount": xmr_amount,
            "currency_id": self.env.ref("base.USD").id,
            "partner_id": self.partner.id,
            "reference": f"TEST-{subaddress[:8]}",
            "provider_reference": subaddress,
            "monero_amount_xmr": xmr_amount,
        })
        tx.sale_order_ids = order
        return order, tx

    @patch(f"{_MODULE}.http_requests.post")
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

    @patch(f"{_MODULE}.http_requests.post")
    def test_no_tx_found(self, mock_post):
        """Subaddress absent from RPC response → raises NoTXFound."""
        mock_post.return_value = _make_rpc_response(None)

        order, tx = self._make_order_and_tx("MissingAddr1")
        with self.assertRaises(NoTXFound):
            order.process_transaction(tx, num_confirmation_required=0)

    @patch(f"{_MODULE}.http_requests.post")
    def test_confirmations_not_met(self, mock_post):
        """unlocked_balance < balance with confirmations required → raises NumConfirmationsNotMet."""
        subaddress = "TestSubAddr2"
        xmr_amount = 1.0
        balance = int(xmr_amount * PICONERO)
        mock_post.return_value = _make_rpc_response(subaddress, balance=balance, unlocked_balance=0)

        order, tx = self._make_order_and_tx(subaddress, xmr_amount)
        with self.assertRaises(NumConfirmationsNotMet):
            order.process_transaction(tx, num_confirmation_required=3)

    def test_already_done_returns_early(self):
        """process_transaction() is a no-op when transaction is already done."""
        order, tx = self._make_order_and_tx("DoneAddr1", xmr_amount=1.0)
        tx._set_done()
        order.process_transaction(tx, num_confirmation_required=0)
        self.assertEqual(tx.state, "done")

    @patch(f"{_MODULE}.http_requests.post")
    def test_zeroconf_ignores_unlocked(self, mock_post):
        """0-conf: balance present but unlocked=0 → still confirms."""
        subaddress = "ZeroConfAddr1"
        xmr_amount = 1.0
        balance = int(xmr_amount * PICONERO)
        mock_post.return_value = _make_rpc_response(subaddress, balance=balance, unlocked_balance=0)

        order, tx = self._make_order_and_tx(subaddress, xmr_amount)
        order.process_transaction(tx, num_confirmation_required=0)

        self.assertEqual(tx.state, "done")
        self.assertEqual(order.state, "sale")

    @patch(f"{_MODULE}.http_requests.post")
    def test_underpayment(self, mock_post):
        """Received less than expected → order NOT confirmed."""
        subaddress = "TestSubAddr3"
        xmr_amount = 2.0
        received = int(0.5 * PICONERO)
        mock_post.return_value = _make_rpc_response(subaddress, balance=received, unlocked_balance=received)

        order, tx = self._make_order_and_tx(subaddress, xmr_amount)
        order.process_transaction(tx, num_confirmation_required=0)

        self.assertNotEqual(tx.state, "done")
        self.assertNotEqual(order.state, "sale")
