import unittest
from unittest.mock import patch, MagicMock
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import json
import logging

_logger = logging.getLogger(__name__)

@tagged('post_install', '-at_install')
class TestPaymentProviderMonero(TransactionCase):
    def setUp(self):
        super(TestPaymentProviderMonero, self).setUp()
        self.PaymentProvider = self.env['payment.provider']
        self.Currency = self.env['res.currency']
        self.MoneroPayment = self.env['monero.payment']
        
        self.currency_usd = self.env.ref('base.USD')
        self.currency_eur = self.env.ref('base.EUR')
        
        self.provider = self.PaymentProvider.create({
            'name': 'Monero Test Provider',
            'code': 'monero_rpc',
            'state': 'enabled',
            'rpc_url': 'http://localhost:38082/json_rpc',
            'rpc_user': 'testuser',
            'rpc_password': 'testpass',
            'wallet_file': 'testwallet',
            'wallet_password': 'walletpass',
            'wallet_dir': '/tmp',
            'network_type': 'mainnet',
            'daemon_rpc_url': 'http://localhost:38081/json_rpc',
            'confirmation_threshold': 10,
            'manual_rates': json.dumps({'USD': 200, 'EUR': 180}),
            'use_subaddresses': True,
        })

        self.test_order = self.env['sale.order'].create({
            'partner_id': self.env['res.partner'].create({'name': 'Test Partner'}).id,
            'order_line': [(0, 0, {
                'product_id': self.env['product.product'].create({
                    'name': 'Test Product',
                    'list_price': 100.0
                }).id,
                'product_uom_qty': 1,
                'price_unit': 100.0,
            })]
        })

    def test_create_monero_provider(self):
        """Test creation of Monero payment provider"""
        self.assertEqual(self.provider.code, 'monero_rpc')
        self.assertEqual(self.provider.network_type, 'mainnet')
        self.assertEqual(self.provider.confirmation_threshold, 10)
        self.assertTrue(self.provider.use_subaddresses)

    @patch('monero.wallet.Wallet')
    @patch('monero.backends.jsonrpc.JSONRPCWallet')
    def test_get_wallet_client_success(self, mock_jsonrpc, mock_wallet):
        """Test successful wallet client initialization"""
        mock_jsonrpc.return_value = MagicMock()
        mock_wallet.return_value = MagicMock()
        
        wallet = self.provider._get_wallet_client()
        self.assertIsNotNone(wallet)

    @patch('monero.wallet.Wallet')
    def test_get_wallet_client_failure(self, mock_wallet):
        """Test wallet client initialization failure"""
        mock_wallet.side_effect = Exception("Connection failed")
        with self.assertRaises(UserError):
            self.provider._get_wallet_client()

    @patch('monero.daemon.Daemon')
    @patch('monero.backends.jsonrpc.JSONRPCDaemon')
    def test_get_daemon_client_success(self, mock_jsonrpc, mock_daemon):
        """Test successful daemon client initialization"""
        mock_jsonrpc.return_value = MagicMock()
        mock_daemon.return_value = MagicMock()
        
        daemon = self.provider._get_daemon()
        self.assertIsNotNone(daemon)

    def test_validate_address(self):
        """Test address validation"""
        self.assertTrue(self.provider._validate_address('testaddress'))
        self.assertTrue(self.provider._validate_address('testaddress', is_subaddress=True))

    @patch('requests.get')
    def test_cron_update_xmr_rates_api_success(self, mock_get):
        """Test successful rate update from API"""
        mock_response = MagicMock()
        mock_response.json.return_value = {'monero': {'usd': 200.0}}
        mock_get.return_value = mock_response
        
        rate = self.provider._cron_update_xmr_rates('USD')
        self.assertEqual(rate, 200.0)

    @patch('requests.get')
    def test_cron_update_xmr_rates_api_failure(self, mock_get):
        """Test rate update falling back to manual rates when API fails"""
        mock_get.side_effect = Exception("API error")
        
        rate = self.provider._cron_update_xmr_rates('USD')
        self.assertEqual(rate, 200.0)  # From manual_rates

    def test_get_manual_rate(self):
        """Test manual rate retrieval"""
        rate = self.provider.get_manual_rate('USD')
        self.assertEqual(rate, 200.0)
        
        rate = self.provider.get_manual_rate('EUR')
        self.assertEqual(rate, 180.0)
        
        rate = self.provider.get_manual_rate('JPY')
        self.assertIsNone(rate)

    @patch('odoo.addons.payment_monero_rpc.models.payment_provider.PaymentProviderMonero._get_wallet_client')
    def test_fetch_wallet_addresses_success(self, mock_wallet):
        """Test successful wallet address fetching"""
        mock_account = MagicMock()
        mock_account.primary_address.return_value = MagicMock(address='addr1')
        mock_account.balance.return_value = MagicMock(balance=1000000000000, unlocked_balance=800000000000)
        mock_account.index = 0
        mock_account.label = "Test Account"
        
        mock_wallet.return_value.accounts.return_value = [mock_account]
        
        result = self.provider.fetch_wallet_addresses()
        self.assertTrue(result)
        self.assertEqual(self.provider.wallet_status, 'ready')
        self.assertEqual(self.provider.account_balance, 1.0)
        self.assertEqual(self.provider.unlocked_balance, 0.8)

    @patch('odoo.addons.payment_monero_rpc.models.payment_provider.PaymentProviderMonero._get_wallet_client')
    def test_fetch_wallet_addresses_failure(self, mock_wallet):
        """Test wallet address fetching failure"""
        mock_wallet.side_effect = Exception("Wallet error")
        
        with self.assertRaises(UserError):
            self.provider.fetch_wallet_addresses()
        
        self.assertEqual(self.provider.wallet_status, 'error')

    @patch('odoo.addons.payment_monero_rpc.models.payment_provider.PaymentProviderMonero._get_wallet_client')
    def test_create_monero_from_fiat_payment_subaddress(self, mock_wallet):
        """Test payment creation with subaddress"""
        mock_wallet.return_value.new_address.return_value = ('subaddr1', 'index1')
        
        payment = self.provider._create_monero_from_fiat_payment(
            order_ref='TEST123',
            amount=100.0,
            currency=self.currency_usd,
            order_id=self.test_order
        )
        
        self.assertEqual(payment.order_ref, 'TEST123')
        self.assertEqual(payment.original_amount, 100.0)
        self.assertEqual(payment.original_currency, 'USD')
        self.assertEqual(payment.address_seller, 'subaddr1')
        self.assertTrue(payment.is_subaddress)

    @patch('odoo.addons.payment_monero_rpc.models.payment_provider.PaymentProviderMonero._get_wallet_client')
    def test_create_monero_from_fiat_payment_integrated(self, mock_wallet):
        """Test payment creation with integrated address"""
        self.provider.use_subaddresses = False
        self.provider.wallet_address_value = 'baseaddr1'
        mock_wallet.return_value.integrated_address.return_value = 'integrated1'
        
        payment = self.provider._create_monero_from_fiat_payment(
            order_ref='TEST123',
            amount=100.0,
            currency=self.currency_usd,
            order_id=self.test_order
        )
        
        self.assertEqual(payment.order_ref, 'TEST123')
        self.assertEqual(payment.address_seller, 'integrated1')
        self.assertFalse(payment.is_subaddress)

    @patch('odoo.addons.payment_monero_rpc.models.payment_provider.PaymentProviderMonero._get_wallet_client')
    def test_create_monero_from_fiat_payment_no_base_address(self, mock_wallet):
        """Test payment creation failure when no base address in integrated mode"""
        self.provider.use_subaddresses = False
        self.provider.wallet_address_value = False
        
        with self.assertRaises(UserError):
            self.provider._create_monero_from_fiat_payment(
                order_ref='TEST123',
                amount=100.0,
                currency=self.currency_usd,
                order_id=self.test_order
            )

    def test_compute_wallet_selection(self):
        """Test wallet address selection computation"""
        self.provider.wallet_addresses = [
            {'address': 'addr1', 'label': 'Account 1'},
            {'address': 'addr2', 'label': 'Account 2'}
        ]
        
        selection = self.provider._compute_wallet_selection()
        self.assertEqual(len(selection), 2)
        self.assertIn(('addr1', 'Account 1 (addr1...addr1)'), selection)

    def test_compute_account_details(self):
        """Test account details computation"""
        self.provider.wallet_addresses = [
            {
                'address': 'addr1',
                'label': 'Account 1',
                'balance': 1.5,
                'unlocked_balance': 1.2,
                'account_index': 0
            }
        ]
        self.provider.wallet_address = 'addr1'
        
        self.provider._compute_account_details()
        self.assertEqual(self.provider.account_balance, 1.5)
        self.assertEqual(self.provider.unlocked_balance, 1.2)
        self.assertEqual(self.provider.account_index, 0)

    def test_inverse_wallet_address(self):
        """Test wallet address inverse method"""
        self.provider.wallet_addresses = [
            {
                'address': 'addr1',
                'label': 'Account 1',
                'balance': 1.5,
                'unlocked_balance': 1.2,
                'account_index': 0
            }
        ]
        self.provider.wallet_address = 'addr1'
        self.provider._inverse_wallet_address()
        
        self.assertEqual(self.provider.wallet_address_value, 'addr1')
        self.assertEqual(self.provider.account_balance, 1.5)

    def test_onchange_wallet_address(self):
        """Test wallet address onchange"""
        self.provider.wallet_addresses = [
            {
                'address': 'addr1',
                'label': 'Account 1',
                'balance': 1.5,
                'unlocked_balance': 1.2,
                'account_index': 0
            }
        ]
        self.provider.wallet_address = 'addr1'
        self.provider._onchange_wallet_address()
        
        self.assertEqual(self.provider.account_balance, 1.5)

    def test_setup_monero_payment_method(self):
        """Test payment method setup"""
        method = self.provider._setup_monero_payment_method()
        self.assertEqual(method.code, 'monero_rpc')
        self.assertEqual(method.name, 'Monero RPC')

    def test_get_compatible_payment_methods(self):
        """Test compatible payment methods"""
        methods = self.provider._get_compatible_payment_methods(
            partner_id=self.test_order.partner_id.id,
            currency_id=self.currency_usd.id
        )
        self.assertEqual(methods.code, 'monero_rpc')

    @patch('odoo.addons.payment_monero_rpc.models.payment_provider.PaymentProviderMonero._get_wallet_client')
    def test_generate_subaddress(self, mock_wallet):
        """Test subaddress generation"""
        mock_wallet.return_value.new_address.return_value = ('subaddr1', 'index1')
        
        result = self.provider._generate_subaddress(self.provider, label='Test')
        self.assertEqual(result['address'], 'subaddr1')
        self.assertEqual(result['address_index'], 'index1')

    @patch('odoo.addons.payment_monero_rpc.models.payment_provider.PaymentProviderMonero._get_wallet_client')
    def test_generate_integrated_address(self, mock_wallet):
        """Test integrated address generation"""
        mock_wallet.return_value.integrated_address.return_value = 'integrated1'
        
        result = self.provider._generate_integrated_address('baseaddr1', 'paymentid1')
        self.assertEqual(result, 'integrated1')

    def test_cron_update_payment_provider(self):
        """Test cron job for provider update"""
        with patch('odoo.addons.payment_monero_rpc.models.payment_provider.PaymentProviderMonero.fetch_wallet_addresses') as mock_fetch:
            self.provider._cron_update_payment_provider()
            mock_fetch.assert_called_once()

    def test_create_monero_from_fiat_payment_public(self):
        """Test public payment creation method"""
        with patch('odoo.addons.payment_monero_rpc.models.payment_provider.PaymentProviderMonero._create_monero_from_fiat_payment') as mock_create:
            mock_create.return_value = MagicMock(
                payment_id='test123',
                address_seller='addr1',
                is_subaddress=True,
                image_qr='qrdata',
                amount=0.5,
                exchange_rate=200.0,
                order_ref='TEST123',
                state='pending',
                expiration=datetime.now(),
                original_amount=100.0,
                original_currency='USD'
            )
            
            result = self.provider.create_monero_from_fiat_payment(
                pos_reference='TEST123',
                amount=100.0,
                currency_name='USD',
                extra_data=None
            )
            
            self.assertTrue(result['success'])
            self.assertEqual(result['payment_id'], 'test123')
