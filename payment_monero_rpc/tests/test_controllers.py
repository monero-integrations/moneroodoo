"""
Unit tests for Monero payment controller integration in Odoo.

This test suite verifies:
- Access and validation of sales orders
- Payment processing for Monero
- QR code generation and rendering
- Status checking, proof and invoice generation
- Error handling
"""

import base64
from unittest.mock import patch, MagicMock
from odoo.tests import HttpCase, tagged
from odoo.exceptions import AccessError, ValidationError, UserError
from odoo.exceptions import MissingError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


@tagged('post_install', '-at_install')
class TestMoneroWebsiteSale(HttpCase):
    """
    Test cases for the Monero payment controller.

    Instantiates the controller directly rather than via the non-existent
    ir.http._get_monero_controller() method.
    """

    def setUp(self):
        """Set up common test data before each test."""
        super().setUp()

        # Fix 12.1: instantiate controller directly — ir.http has no _get_monero_controller()
        from odoo.addons.payment_monero_rpc.controllers.main import MoneroWebsiteSale
        self.controller = MoneroWebsiteSale()

        self.currency_usd = self.env.ref('base.USD')

        self.provider = self.env['payment.provider'].create({
            'name': 'Monero RPC',
            'code': 'monero_rpc',
            'state': 'enabled',
            'confirmation_threshold': 10,
        })

        self.partner = self.env['res.partner'].create({
            'name': 'Test Customer',
            'email': 'customer@test.com',
        })

        self.product = self.env['product.product'].create({
            'name': 'Test Product',
            'list_price': 100.0,
            'sale_ok': True,
        })

        self.order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'price_unit': self.product.list_price,
            })]
        })

        self.payment = self.env['monero.payment'].create({
            'payment_id': 'test_payment_123',
            'address_seller': 'monero_address_123',
            'amount': 0.123456789012,
            'original_amount': 100.0,
            'original_currency': self.currency_usd.name,
            'exchange_rate': 810.0,
            'order_ref': self.order.name,
            'state': 'pending',
            'expiration': datetime.now() + timedelta(hours=1),
            'sale_order_id': self.order.id,
        })

    # ------------------------------------------------------------------
    # Fix 12.2: _validate_order_access has no _logger.debug call;
    #           remove the mock_debug assertion, just check the return value.
    # ------------------------------------------------------------------
    def test_validate_order_access(self):
        """Valid token returns the order; invalid token raises AccessError."""
        # Valid token: must succeed
        result = self.controller._validate_order_access(
            self.order.id, self.order.access_token)
        self.assertEqual(result.id, self.order.id)

        # Issue 92: invalid token must be rejected — the old test never tested this
        from odoo.exceptions import AccessError, MissingError
        with self.assertRaises((AccessError, MissingError)):
            self.controller._validate_order_access(self.order.id, 'invalid_token_xyz')

    # ------------------------------------------------------------------
    # Fix 12.3: _validate_and_lock_order raises MissingError (not
    #           ValidationError) for invalid token; the test must match
    #           the actual exception.  We also accept ValidationError as
    #           a valid security rejection to keep the test robust.
    # ------------------------------------------------------------------
    def test_validate_and_lock_order_invalid_token(self):
        """Invalid access token is rejected."""
        with self.assertRaises((MissingError, ValidationError, UserError)):
            self.controller._validate_and_lock_order(
                self.order.id, 'invalid_token')

    def test_validate_and_lock_order_cancelled(self):
        """Cancelled order raises ValidationError on lock attempt."""
        self.order.action_cancel()
        with self.assertRaises((MissingError, ValidationError, UserError)):
            self.controller._validate_and_lock_order(
                self.order.id, self.order.access_token)

    # ------------------------------------------------------------------
    # Fix 12.4: _process_monero_payment signature is now (order_id, **kwargs)
    #           and fetches provider internally — pass order_id directly.
    # ------------------------------------------------------------------
    @patch('odoo.addons.payment_monero_rpc.controllers.main.request')
    def test_process_monero_payment(self, mock_request):
        """Monero payment is created with valid token; rejected without one."""
        mock_request.env = self.env
        mock_request.session = {}

        with patch.object(self.provider, '_create_monero_from_fiat_payment',
                          return_value=self.payment):
            # Issue 93: authenticated path (valid token)
            result = self.controller._process_monero_payment(
                order_id=self.order.id,
                access_token=self.order.access_token
            )

        self.assertTrue(result['success'])
        self.assertEqual(result['payment_id'], 'test_payment_123')

        # Issue 93: unauthenticated path must be rejected
        result_unauth = self.controller._process_monero_payment(
            order_id=self.order.id,
            access_token=''
        )
        self.assertFalse(result_unauth.get('success', True))

    # ------------------------------------------------------------------
    # Fix 12.5: session mock must have at least pop(); use a real dict-like
    #           object so payment_page doesn't crash on .pop()
    # ------------------------------------------------------------------
    @patch('odoo.addons.payment_monero_rpc.controllers.main.request')
    def test_payment_page_reads_db_on_empty_session(self, mock_request):
        """payment_page falls back to DB record when session is empty."""
        mock_request.env = self.env
        mock_request.session = {}  # no monero_payment_data
        mock_request.render = MagicMock(return_value='rendered')

        result = self.controller.payment_page(self.payment.id)
        mock_request.render.assert_called_once()
        ctx = mock_request.render.call_args[0][1]
        self.assertIn('payment', ctx)
        self.assertEqual(ctx['payment']['id'], self.payment.id)

    @patch('odoo.addons.payment_monero_rpc.controllers.main.request')
    def test_check_payment_status_pending(self, mock_request):
        """Status check returns pending for a new payment."""
        mock_request.env = self.env

        with patch.object(self.payment, 'check_payment_status',
                          return_value={'state': 'pending', 'amount_received': 0,
                                        'confirmations': 0, 'transactions': []}):
            result = self.controller.check_payment_status('test_payment_123')

        self.assertEqual(result['status'], 'pending')
        # Fix: amount_received field (not amount) is returned
        self.assertIn('amount_received', result)

    @patch('odoo.addons.payment_monero_rpc.controllers.main.request')
    def test_check_payment_status_not_found(self, mock_request):
        """Unknown payment_id returns error dict."""
        mock_request.env = self.env
        result = self.controller.check_payment_status('nonexistent_id')
        self.assertEqual(result['status'], 'error')

    @patch('odoo.addons.payment_monero_rpc.controllers.main.request')
    def test_generate_qr_code_returns_png(self, mock_request):
        """generate_qr_code returns PNG with valid token; 404 without token."""
        mock_request.env = self.env
        fake_png = base64.b64encode(b'\x89PNG\r\nfake')
        self.payment.image_qr = fake_png
        mock_request.make_response = MagicMock(return_value='response')
        mock_request.not_found = MagicMock(return_value='404')

        # Issue 94: valid token should succeed
        result = self.controller.generate_qr_code(
            self.payment.id, access_token=self.order.access_token)
        mock_request.make_response.assert_called_once()

        # Issue 94: no token must be blocked (not_found)
        mock_request.make_response.reset_mock()
        mock_request.not_found.reset_mock()
        result_unauth = self.controller.generate_qr_code(
            self.payment.id, access_token=None)
        mock_request.not_found.assert_called()

    @patch('odoo.addons.payment_monero_rpc.controllers.main.request')
    def test_generate_invoice_requires_access_token(self, mock_request):
        """generate_invoice with wrong access token returns 404."""
        mock_request.env = self.env
        mock_request.not_found = MagicMock(return_value='404')

        result = self.controller.generate_invoice(
            self.payment.id, access_token='wrong_token')
        mock_request.not_found.assert_called_once()

    @patch('odoo.addons.payment_monero_rpc.controllers.main.request')
    def test_generate_proof_unconfirmed_returns_404(self, mock_request):
        """generate_proof on a non-confirmed payment returns 404."""
        mock_request.env = self.env
        mock_request.not_found = MagicMock(return_value='404')

        result = self.controller.generate_proof(self.payment.id)
        mock_request.not_found.assert_called_once()

    @patch('odoo.addons.payment_monero_rpc.controllers.main.request')
    def test_get_translations_returns_empty_list(self, mock_request):
        """get_translations returns [] in Odoo 17+ (ir.translation removed)."""
        mock_request.env = self.env
        result = self.controller.get_translations('en_US')
        self.assertEqual(result, [])
