import odoo.tests.common as common
import unittest
from unittest.mock import patch, MagicMock
from odoo.tests import HttpCase, tagged
from odoo.exceptions import AccessError, ValidationError, UserError
from werkzeug.exceptions import NotFound
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

@tagged('post_install', '-at_install')
class TestMoneroWebsiteSale(HttpCase):
    def setUp(self):
        super(TestMoneroWebsiteSale, self).setUp()
        self.controller = self.env['ir.http']._get_monero_controller()
        
        self.currency_xmr = self.env['res.currency'].create({
            'name': 'XMR',
            'symbol': 'ɱ',
            'rounding': 0.000000000001,
        })
        
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

    def test_validate_order_access(self):
        """Test order access validation"""
        with patch.object(_logger, 'debug') as mock_debug:
            result = self.controller._validate_order_access(self.order.id, self.order.access_token)
            self.assertEqual(result, self.order.sudo())
            mock_debug.assert_called_once()

    def test_validate_and_lock_order_success(self):
        """Test successful order validation and locking"""
        order_sudo = self.controller._validate_and_lock_order(self.order.id, self.order.access_token)
        self.assertEqual(order_sudo, self.order.sudo())

    def test_validate_and_lock_order_invalid_token(self):
        """Test order validation with invalid access token"""
        with self.assertRaises(ValidationError):
            self.controller._validate_and_lock_order(self.order.id, 'invalid_token')

    def test_validate_and_lock_order_cancelled(self):
        """Test validation of cancelled order"""
        self.order.action_cancel()
        with self.assertRaises(ValidationError):
            self.controller._validate_and_lock_order(self.order.id, self.order.access_token)

    def test_process_monero_payment(self):
        """Test Monero payment processing"""
        mock_provider = MagicMock()
        mock_provider.get_xmr_rate.return_value = 810.0
        mock_provider._create_monero_from_fiat_payment.return_value = self.payment
        
        with patch('odoo.http.request.env', return_value=self.env):
            with patch('odoo.http.request.render', return_value=MagicMock()):
                result = self.controller._process_monero_payment(
                    order_sudo=self.order.id,
                    provider=self.provider.id,
                )
                
                self.assertTrue(result['success'])
                self.assertEqual(result['payment_id'], 'test_payment_123')
                self.assertEqual(result['payment']['order_ref'], self.order.name)

    def test_process_monero_payment_invalid_currency(self):
        """Test payment processing with invalid currency"""
        mock_provider = MagicMock()
        mock_provider.get_xmr_rate.return_value = 0
        
        with patch('odoo.http.request.env', return_value=self.env):
            with self.assertRaises(UserError):
                self.controller._process_monero_payment(
                    order_sudo=self.order.id,
                    provider=self.provider.id,
                )

    def test_monero_payment_processor_success(self):
        """Test payment processor with valid parameters"""
        with patch('odoo.http.request.redirect') as mock_redirect:
            self.controller.monero_payment_processor(
                order_id=self.order.id,
                access_token=self.order.access_token,
                provider_id=self.provider.id,
                amount=self.order.amount_total
            )
            mock_redirect.assert_called_once()

    def test_monero_payment_processor_missing_params(self):
        """Test payment processor with missing parameters"""
        with self.assertRaises(ValueError):
            self.controller.monero_payment_processor(
                order_id=self.order.id,
                access_token=self.order.access_token
            )

    def test_check_payment_status(self):
        """Test payment status checking"""
        with patch('odoo.http.request.env', return_value=self.env):
            result = self.controller.check_payment_status('test_payment_123')
            self.assertEqual(result['status'], 'pending')
            self.assertEqual(result['status_message'], self.payment._get_status_message())

    def test_check_payment_status_not_found(self):
        """Test status check for non-existent payment"""
        with patch('odoo.http.request.env', return_value=self.env):
            result = self.controller.check_payment_status('nonexistent_payment')
            self.assertEqual(result['status'], 'error')
            self.assertEqual(result['error'], 'Payment not found')

    def test_generate_qr_code(self):
        """Test QR code generation"""
        with patch('odoo.http.request.make_response') as mock_response:
            with patch('qrcode.QRCode') as mock_qrcode:
                self.controller.generate_qr_code(self.payment.id)
                mock_qrcode.assert_called_once()
                mock_response.assert_called_once()

    def test_generate_qr_code_not_found(self):
        """Test QR code generation for non-existent payment"""
        with self.assertRaises(NotFound):
            self.controller.generate_qr_code(999999)

    def test_payment_page(self):
        """Test payment page rendering"""
        test_data = {
            'address_seller': 'test_address',
            'amount_str': '0.123456789012',
            'order_ref': 'TEST123',
        }
        
        with patch('odoo.http.request.session', {'monero_payment_data': test_data}):
            with patch('odoo.http.request.render') as mock_render:
                self.controller.payment_page(self.payment.id)
                mock_render.assert_called_once()
                self.assertIn('monero_uri', mock_render.call_args[0][1])

    def test_payment_page_session_expired(self):
        """Test payment page with expired session"""
        with patch('odoo.http.request.session', {}):
            with patch('odoo.http.request.redirect') as mock_redirect:
                self.controller.payment_page(self.payment.id)
                mock_redirect.assert_called_once_with('/shop?error=session_expired')

    def test_generate_invoice(self):
        """Test invoice generation"""
        with patch('odoo.http.request.make_response') as mock_response:
            with patch('odoo.http.request.env') as mock_env:
                mock_env['ir.actions.report']._render_qweb_pdf.return_value = [b'pdf_content', 'pdf']
                self.controller.generate_invoice(self.payment.id)
                mock_response.assert_called_once()

    def test_generate_invoice_not_found(self):
        """Test invoice generation for non-existent payment"""
        with self.assertRaises(NotFound):
            self.controller.generate_invoice(999999)

    def test_generate_proof(self):
        """Test payment proof generation"""
        self.payment.state = 'confirmed'
        with patch('odoo.http.request.make_response') as mock_response:
            with patch('odoo.http.request.env') as mock_env:
                mock_env['ir.actions.report']._render_qweb_pdf.return_value = [b'pdf_content', 'pdf']
                self.controller.generate_proof(self.payment.id)
                mock_response.assert_called_once()

    def test_generate_proof_not_confirmed(self):
        """Test proof generation for unconfirmed payment"""
        with self.assertRaises(NotFound):
            self.controller.generate_proof(self.payment.id)

    def test_get_translations(self):
        """Test translation retrieval"""
        test_translation = self.env['ir.translation'].create({
            'name': 'payment_monero_rpc.field,value',
            'type': 'model',
            'lang': 'en_US',
            'module': 'payment_monero_rpc',
            'src': 'Test Source',
            'value': 'Test Translation',
        })
        
        with patch('odoo.http.request.env', return_value=self.env):
            result = self.controller.get_translations('en_US')
            self.assertGreaterEqual(len(result), 1)
            self.assertEqual(result[0]['src'], 'Test Source')
