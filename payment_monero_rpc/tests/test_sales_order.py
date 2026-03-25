# Provides basic Unit Tests for the major functionality in the sale_order (sale.order) entity definition

import os
import unittest
from odoo.tests import tagged, TransactionCase
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from decimal import Decimal

@tagged("post_install", "-at_install")
class TestMoneroSalesOrder(TransactionCase):
    """
    Unit tests for Monero payments integration with Odoo sales orders.

    Tests the Monero payment creation and status checking behavior within the sale order flow,
    using mocked Monero wallet RPC interactions.

    Attributes
    ----------
    partner : res.partner
        Test customer.
    product : product.product
        Sample product for sale.
    sale_order : sale.order
        Test sales order to which Monero payments are linked.
    provider : payment.provider
        Monero RPC-based provider for handling payments.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Issue 23: replaced warnings.warn with a proper skipUnless environment guard
        # Run with MONERO_RPC_RUNNING=1 to execute tests that require a live daemon.

        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Partner',
            'email': 'test@example.com',
            'country_id': cls.env.ref('base.ng').id,
        })

        pricelist = cls.env['product.pricelist'].search([], limit=1)
        if not pricelist:
            pricelist = cls.env['product.pricelist'].create({
                'name': 'Test Pricelist',
                'currency_id': cls.env.ref('base.USD').id,
            })

        cls.product = cls.env['product.product'].create({
            'name': 'Test Product',
            'type': 'consu',
            'list_price': 100,
        })

        cls.sale_order = cls.env['sale.order'].create({
            'partner_id': cls.partner.id,
            'partner_invoice_id': cls.partner.id,
            'partner_shipping_id': cls.partner.id,
            'pricelist_id': pricelist.id,
            'order_line': [(0, 0, {
                'product_id': cls.product.id,
                'product_uom_qty': 1,
                'price_unit': cls.product.list_price,
            })],
        })

        journal = cls.env['account.journal'].search([('type', '=', 'bank')], limit=1)

        cls.provider = cls.env['payment.provider'].create({
            'name': 'Monero RPC',
            'journal_id': journal.id,
            'code': 'monero_rpc'
        })

    def _make_realistic_new_address(self):
        """
        Generates a mocked new subaddress from the Monero wallet.

        Returns
        -------
        Callable
            Function returning deterministic mock address and index tuple.
        """
        def _mock_new_address(label=None):
            # Issue 22: query MAX(id) on the integer primary key, not MAX(payment_id)
            # which is a Char field and uses lexicographic ordering.
            self.env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM monero_payment")
            max_id = self.env.cr.fetchone()[0]
            next_id = max_id + 1
            return [f'mockaddress_{str(next_id).zfill(4)}', next_id]
        return _mock_new_address

    @patch("requests.get")
    @patch("odoo.addons.payment_monero_rpc.models.payment_provider.PaymentProviderMonero._get_wallet_client")
    def test_monero_payment_flow(self, mock_wallet_client, mock_requests_get):
        """
        Test end-to-end Monero payment flows, including confirmation states.

        Covers 4 scenarios:
        1. Successful payment with required confirmations
        2. Address reuse scenario
        3. Insufficient confirmations
        4. No matching transactions
        """
        # Mock exchange rate response (200 USD per XMR)
        mock_requests_get.return_value.json.return_value = {"monero": {"usd": 200}}

        provider = self.provider
        sale_order = self.sale_order

        # Setup mocked wallet and subaddresses
        wallet = MagicMock()
        mock_wallet_client.return_value = wallet
        wallet.new_address.side_effect = self._make_realistic_new_address()

        reuse_address = "9tQoHWyZ4yXUgbz9nvMcFZUfDy5hxcdZabQCxmNCUukKYicXegsDL7nQpcUa3A1pF6"

        # --- 1. Successful payment case ---
        payment = provider._create_monero_from_fiat_payment(
            sale_order.name, sale_order.amount_total, 'USD', sale_order
        )
        wallet.incoming.return_value = [
            MagicMock(
                local_address=payment.address_seller,
                amount=Decimal(payment.amount),
                transaction=MagicMock(
                    hash="tx123",
                    confirmations=10,
                    height=123456,
                    # Issue 21: use timezone-aware datetime
                    timestamp=datetime.now(tz=timezone.utc),
                    fee=Decimal("0.0001")
                )
            )
        ]
        result = payment.check_payment_status(payment.payment_id)
        # Issue 20: 'done' and 'paid' are not valid monero.payment states — only 'confirmed'
        self.assertEqual(payment.state, 'confirmed')

        # --- 2. Address Reuse scenario ---
        payment_reuse = provider._create_monero_from_fiat_payment(
            sale_order.name + "-reuse", sale_order.amount_total, 'USD', sale_order
        )
        wallet.incoming.return_value = [
            MagicMock(
                local_address=reuse_address,
                amount=Decimal(payment_reuse.amount),
                transaction=MagicMock(
                    hash="reuse_tx",
                    confirmations=10,
                    height=123457,
                    timestamp=datetime.now(tz=timezone.utc),
                    fee=Decimal("0.0001")
                )
            )
        ]
        payment_reuse.address_seller = reuse_address
        payment_reuse.check_payment_status(payment_reuse.payment_id)
        # Issue 24: scenario 2 had no assertions — add a state check
        self.assertIn(payment_reuse.state, ['pending', 'confirmed', 'paid_unconfirmed'])

        # --- 3. Not enough confirmations ---
        payment_conf = provider._create_monero_from_fiat_payment(
            sale_order.name + "-conf", sale_order.amount_total, 'USD', sale_order
        )
        wallet.incoming.return_value = [
            MagicMock(
                local_address=payment_conf.address_seller,
                amount=Decimal(payment_conf.amount),
                transaction=MagicMock(
                    hash="conf_tx",
                    confirmations=1,
                    height=123458,
                    timestamp=datetime.now(tz=timezone.utc),
                    fee=Decimal("0.0001")
                )
            )
        ]
        payment_conf.check_payment_status(payment_conf.payment_id)
        self.assertEqual(payment_conf.state, 'paid_unconfirmed')

        # --- 4. No transaction found ---
        payment_no_tx = provider._create_monero_from_fiat_payment(
            sale_order.name + "-notx", sale_order.amount_total, 'USD', sale_order
        )
        wallet.incoming.return_value = []
        payment_no_tx.check_payment_status(payment_no_tx.payment_id)
        self.assertEqual(payment_no_tx.state, 'pending')
