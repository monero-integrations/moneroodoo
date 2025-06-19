import logging
import secrets
import base64
import hashlib
import json
import os
from io import BytesIO
from datetime import datetime, timedelta

import qrcode
import monero
import requests
import urllib.parse
from monero.wallet import Wallet
from monero.backends.jsonrpc import JSONRPCWallet
from monero.daemon import Daemon, JSONRPCDaemon
from monero.address import Address, SubAddress

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

class PaymentProviderMonero(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('monero_rpc', 'Monero (RPC)')],
        ondelete={'monero_rpc': 'set default'}
    )

    rpc_url = fields.Char(
        string="URL",
        default=lambda self: self.env['ir.config_parameter'].sudo().get_param(
            'monero.rpc_url', 'http://localhost:38082/json_rpc'),
        help="URL of Monero wallet RPC (e.g., http://localhost:38082/json_rpc)"
    )

    rpc_user = fields.Char(string='RPC Username')
    rpc_password = fields.Char(string='RPC Password')
    wallet_file = fields.Char(string='Wallet File') 
    wallet_password = fields.Char(string='Wallet Password')
    wallet_dir = fields.Char(string='Wallet Directory') 
    network_type = fields.Selection(
        selection=[
            ('mainnet', 'Mainnet'),
            ('stagenet', 'Stagenet'),
            ('testnet', 'Testnet')
        ],
        string='Network',
        default='mainnet'
    )

    daemon_rpc_url = fields.Char(
        string="Daemon URL",
        default=lambda self: self.env['ir.config_parameter'].sudo().get_param(
            'monero.daemon_rpc_url', 'http://localhost:38081/json_rpc'),
        help="URL of Daemon RPC (e.g., http://localhost:38081/json_rpc)"
    )
    
    confirmation_threshold = fields.Integer(
        string="Confirmations",
        default=lambda self: int(
            self.env['ir.config_parameter'].sudo().get_param(
                'monero.required_confirmations', 2) or 2),
        help="Number of blockchain confirmations required before considering payment complete"
    )

    rpc_timeout = fields.Integer(
        string='Timeout',
        default=180,
        help="Number of seconds before a timeout is issue if not connected"
    )

    restaurant_mode = fields.Boolean(
        string='Restaurant Mode',
        help="Check to determine whether or not the shop is a restaurant"
    )

    exchange_rate_api = fields.Char(
        string="Xchange API",
        default="https://api.coingecko.com/api/v3/simple/price"
    )

    manual_rates = fields.Json(
        string="Manual Rates",
        default={"USD": 200, "EUR": 180}
    )

    wallet_addresses = fields.Json(
        string="Available Wallets",
        default=[],
        readonly=True,
        help="Cached list of wallet addresses from last refresh"
    )
        
    use_subaddresses = fields.Boolean(
        string="Use Subaddresses",
        default=True,
        help="Enable modern subaddresses (recommended). Disable for legacy Payment IDs."
    )
     
    wallet_address_value = fields.Char(string="Wallet Address Value")
    
    wallet_address = fields.Selection(
        selection='_compute_wallet_selection',
        inverse='_inverse_wallet_address',
        string="Monero Wallet Address"
    )
    
    wallet_status = fields.Char(string="Wallet Status")
    
    account_balance = fields.Float(
        string="Balance",
        readonly=True,
        digits=(12, 12),
        compute='_compute_account_details'
    )
    unlocked_balance = fields.Float(
        string="Unlocked Balance",
        readonly=True,
        digits=(12, 12),
        compute='_compute_account_details'
    )
    account_index = fields.Integer(
        string="Account Index",
        readonly=True,
        compute='_compute_account_details'
    )

    def _get_default_monero_image(self):
        """Return the default Monero logo in base64 format."""
        image_path = '/payment_monero_rpc/static/src/img/logo.png'
        try:
            with open(image_path, 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8')
        except IOError:
            return False

    image_128 = fields.Image(default=_get_default_monero_image)
    
    @api.model
    def _get_monero_provider(self):
        """Helper method to get the Monero payment provider"""
        return self.env['payment.provider'].search([('code', '=', 'monero_rpc')], limit=1)

    def _get_daemon(self):
        """Initialize and return Monero Daemon RPC client"""
        try:
            host = "127.0.0.1"
            port = 38082
            provider = self._get_monero_provider()
            if provider.daemon_rpc_url:
                parsed_url = urllib.parse.urlparse(provider.daemon_rpc_url)
                host = parsed_url.hostname or "127.0.0.1"
                port = parsed_url.port or 38082      
            
            daemon_rpc = monero.daemon.Daemon(
                JSONRPCDaemon(
                    host=host,
                    port=port,
                    user=provider.rpc_user or None,
                    password=provider.rpc_password or None,
                    timeout=provider.rpc_timeout or 180
                )
            )        
            return daemon_rpc
        except Exception as e:
            _logger.error("Daemon connection failed: %s", str(e))
            raise UserError(_("Could not connect to Monero daemon. Please check your RPC settings."))

    def _get_wallet_client(self):
        """Initialize Monero wallet client"""
        try:
            provider = self.env['payment.provider'].search([('code', '=', 'monero_rpc')], limit=1)
            _logger.info("RPC Wallet: %s %s %s", provider.rpc_url, provider.rpc_user, provider.rpc_timeout)
            host = "127.0.0.1"
            port = 38082
            if provider.rpc_url:
                parsed_url = urllib.parse.urlparse(provider.rpc_url)
                host = parsed_url.hostname or "127.0.0.1"
                port = parsed_url.port or 38082      
            
            wallet_path = os.path.join(provider.wallet_dir, provider.wallet_file)
            if not os.path.exists(wallet_path):
                raise UserError(_("Wallet file not found at: %s") % wallet_path)
                
            wallet_name = os.path.splitext(os.path.basename(wallet_path))[0]
                    
            wallet = Wallet(
                JSONRPCWallet(
                    host=host,
                    port=port,
                    user=provider.rpc_user,
                    password=provider.rpc_password,
                    timeout=180)
            )                     

            return wallet
        except Exception as e:
            _logger.error("Wallet connection failed: %s", str(e))
            raise UserError(_("Could not connect to Monero wallet. Please check your RPC settings."))
        
    def _get_daemon_client(self):
        """Initialize Monero daemon client"""
        try:
            return Daemon(
                host=self.daemon_rpc_url or "http://127.0.0.1:38081",
                timeout=self.rpc_timeout
            )
        except Exception as e:
            _logger.error("Daemon connection failed: %s", str(e))
            raise UserError(_("Could not connect to Monero daemon. Please check your RPC settings."))

    def _validate_address(self, addr_str, is_subaddress = True):
        return True
        
    @api.model
    def _cron_update_payment_provider(self):
        """Update Monero Payment Provider"""
        provider = self.env['payment.provider'].search([('code', '=', 'monero_rpc')], limit=1)
        if provider:
            provider.fetch_wallet_addresses()

    def get_monero_provider(self):
        return self.search([('code', '=', 'monero_rpc')], limit=1)

    def _update_account_from_cache(self, cached_data):
        """Update account details from cached wallet data"""
        self.write({
            'account_balance': cached_data.get('balance', 0),
            'unlocked_balance': cached_data.get('unlocked_balance', 0),
            'account_index': cached_data.get('account_index', 0)
        })

    def _create_monero_from_fiat_payment(self, order_ref, amount, currency, order_id):
        """Create a payment with proper address generation based on configuration"""
        order_currency = currency.name if hasattr(currency, 'name') else currency
        rate = self.get_xmr_rate(order_currency)
        if not rate:
            raise UserError(_("Could not get exchange rate for %s") % currency)
            
        provider = self.env['payment.provider'].search([('code', '=', 'monero_rpc')], limit=1)
            
        try:
            wallet = provider._get_wallet_client()
            
            if provider.use_subaddresses:
                label = f"Order_{order_ref}"
                subaddress = wallet.new_address(label=label)
                _logger.info("New subaddress: %s", subaddress)
                if not self._validate_address(subaddress[0], is_subaddress=True):
                    raise UserError(_("Generated invalid subaddress for current network"))
                
                payment_values = {
                    'payment_id': subaddress[1],
                    'address_seller': subaddress[0],
                    'is_subaddress': True,
                }
            else:
                payment_id = secrets.token_hex(8)  # 8-byte payment ID
                if not provider.wallet_address_value:
                    raise UserError(_("No base wallet address configured for payment ID mode"))
                
                integrated_address = wallet.integrated_address(
                    payment_id=payment_id,
                    address=provider.wallet_address_value
                )
                if not provider._validate_address(integrated_address):
                    raise UserError(_("Generated invalid integrated address"))
                
                payment_values = {
                    'payment_id': payment_id,
                    'address_seller': integrated_address,
                    'is_subaddress': False
                }
                
            _logger.info("Payment Values: %s", payment_values)

            payment = self.env['monero.payment'].sudo().create({
                **payment_values,
                'amount': amount / rate,
                'exchange_rate': rate,
                'currency': 'XMR',
                'order_ref': order_ref,
                'state': 'pending',
                'expiration': fields.Datetime.add(fields.Datetime.now(), hours=24),
                'original_amount': amount,
                'original_currency': order_currency,
                **({'sale_order_id': order_id.id} if order_id else {})
            })

            payment._compute_qr_code()
            return payment

        except Exception as e:
            _logger.error("Payment creation failed: %s", str(e), exc_info=True)
            raise UserError(_("Failed to create payment: %s") % str(e))

    @api.model
    def create_monero_from_fiat_payment(self, pos_reference, amount, currency_name, extra_data=None):
        """Public method to create fiat payment"""
        result = self._create_monero_from_fiat_payment(pos_reference, amount, currency_name, extra_data)
        
        if hasattr(result, '_fields'):  # Check if it's an Odoo model
            return {
                'payment_id': result.payment_id,
                'address_seller': result.address_seller,
                'is_subaddress': result.is_subaddress,
                'image_qr': result.image_qr,
                'amount': result.amount,
                'exchange_rate': result.exchange_rate,
                'order_ref': result.order_ref,
                'state': 'pending',
                'expiration': result.expiration,
                'original_amount': result.original_amount,
                'original_currency': result.original_currency,
                'success': True
            }
        elif isinstance(result, dict):
            return result
        else:
            return {
                'error': str(result) if result else 'Unknown error',
                'success': False
            }

    def _generate_subaddress(self, provider, label=None):
        """Generate and validate a subaddress for the correct network"""
        try:
            wallet = self._get_wallet_client()
            subaddress = wallet.new_address(label=label or f"Payment_{fields.Datetime.now()}")
            
            if not self._validate_address(subaddress[0], is_subaddress=True):
                raise UserError(_("Wallet generated invalid address %s for network %s") % 
                              (subaddress[0], self.network_type))
            
            return {
                'address_index': subaddress[1],
                'address': subaddress[0]
            }
        except Exception as e:
            _logger.error("Subaddress generation failed: %s", str(e))
            raise UserError(_("Address generation failed. Please check wallet configuration"))

    def _generate_integrated_address(self, base_address, payment_id):
        """Generate integrated address for payment ID mode"""
        try:
            wallet = self._get_wallet_client()
            return wallet.integrated_address(
                payment_id=payment_id,
                address=base_address
            )
        except Exception as e:
            _logger.error("Integrated address generation failed: %s", str(e))
            return base_address

    def get_xmr_rate(self, currency):
        """Get current XMR exchange rate for display"""
        return self._cron_update_xmr_rates(currency)

    def _compute_wallet_selection(self):
        """Generate selection options from wallet_addresses"""
        results = []
        for provider in self:
            if not provider.wallet_addresses:
                continue
                
            for addr in provider.wallet_addresses:
                if not isinstance(addr, dict):
                    continue
                    
                address_val = addr.get('address')
                label = addr.get('label', 'No label')
                
                if address_val:
                    display = f"{label} ({address_val[:6]}...{address_val[-4:]})"
                    results.append((address_val, display))
        
        return results

    @api.depends('wallet_address')
    def _compute_account_details(self):
        """Automatically update balance when address changes"""
        for provider in self:
            if not provider.wallet_address:
                provider.account_balance = 0
                provider.unlocked_balance = 0
                provider.account_index = 0
                continue

            try:
                wallet = provider._get_wallet_client()
                balance = wallet.balance()
                
                provider.account_balance = balance.balance / 1e12
                provider.unlocked_balance = balance.unlocked_balance / 1e12
                provider.account_index = 0  # Will be updated in fetch_wallet_addresses
            except Exception as e:
                _logger.error("Failed to update account details: %s", str(e))
                provider.account_balance = 0
                provider.unlocked_balance = 0
                provider.account_index = 0

    def _get_account_index(self, address):
        """Get account index from address"""
        try:
            wallet = self._get_wallet_client()
            return wallet.address_index(address)
        except Exception:
            return 0

    @api.model
    def _setup_monero_payment_method(self):
        """Create or update the Monero payment method record"""
        payment_method = self.env['payment.method'].search(
            [('code', '=', 'monero_rpc')], limit=1)

        if not payment_method:
            payment_method = self.env['payment.method'].create({
                'name': 'Monero RPC',
                'code': 'monero_rpc',
                'image': self._get_default_monero_image(),
                'support_tokenization': False,
                'support_express_checkout': False,
                'support_refund': 'none',
            })
        return payment_method

    def _get_compatible_payment_methods(self, partner_id, currency_id=None, **kwargs):
        """Override to include Monero as compatible payment method"""
        payment_methods = super()._get_compatible_payment_methods(
            partner_id, currency_id, **kwargs)

        if self.code == 'monero_rpc' and self.state == 'enabled':
            monero_method = self._setup_monero_payment_method()

            if currency_id and monero_method.supported_currency_ids:
                if currency_id not in monero_method.supported_currency_ids.ids:
                    return payment_methods

            partner = self.env['res.partner'].browse(partner_id)
            if partner.country_id and monero_method.supported_country_ids:
                if partner.country_id.id not in monero_method.supported_country_ids.ids:
                    return payment_methods

            payment_methods = monero_method

        return payment_methods
        
    def get_manual_rate(self, currency):
        """Safely get manual rate from JSON string for a currency"""
        try:
            currency_name = currency if isinstance(currency, str) else getattr(currency, 'name', None) or currency.name
            if not currency_name:
                return None
                
            rates = self.manual_rates
            if isinstance(rates, str):
                try:
                    rates = json.loads(rates)
                except json.JSONDecodeError:
                    return None
                    
            if isinstance(rates, dict):
                return rates.get(currency_name)
                
            return None
        except Exception:
            return None        

    @api.model
    def _cron_update_xmr_rates(self, currency='USD'):
        """Get current XMR exchange rate"""
        currency = currency.upper()
        provider = self.env['payment.provider'].search([('code', '=', 'monero_rpc')], limit=1)
        
        try:
            response = requests.get(
                provider.exchange_rate_api,
                params={
                    'ids': 'monero',
                    'vs_currencies': currency.lower()},
                timeout=5
            )
            data = response.json()
            return data.get('monero', {}).get(currency.lower()) or \
                self.get_manual_rate(currency)
        except Exception as e:
            _logger.error("Error fetching exchange rate: %s", str(e))
            return self.get_manual_rate(currency)

    def fetch_wallet_addresses(self):
        """Fetch all wallet accounts and their primary addresses with balances"""
        for provider in self:
            try:
                wallet = provider._get_wallet_client()
                accounts = wallet.accounts()
                wallet_data = []

                for account in accounts:
                    addr = account.primary_address()
                    balance = account.balance()
                    
                    wallet_data.append({
                        'address': addr.address,
                        'label': account.label or f"Account {account.index}",
                        'account_index': account.index,
                        'balance': balance.balance / 1e12,
                        'unlocked_balance': balance.unlocked_balance / 1e12,
                        'base_address': addr.address
                    })

                if wallet_data:
                    provider.write({
                        'wallet_addresses': wallet_data,
                        'wallet_address': wallet_data[0]['address'],
                        'account_balance': wallet_data[0]['balance'],
                        'unlocked_balance': wallet_data[0]['unlocked_balance'],
                        'account_index': wallet_data[0]['account_index'],
                        'wallet_status': 'ready'
                    })
                else:
                    provider.write({'wallet_status': 'empty'})

                return True

            except Exception as e:
                _logger.error("Wallet operation failed: %s", str(e), exc_info=True)
                provider.write({'wallet_status': 'error'})
                raise UserError(str(e)) from e

    def _handle_fetch_error(self, provider):
        """Handle error state for wallet fetch"""
        provider.write({
            'wallet_addresses': [],
            'wallet_address': False,
            'wallet_address_value': False,
            'account_balance': 0,
            'unlocked_balance': 0,
            'account_index': 0
        })

    def _get_cached_wallet_selection(self):
        """Get selection options from cache WITHOUT RPC calls"""
        self.ensure_one()
        if not self.wallet_addresses:
            return []
        return [(addr['address'], addr['label']) for addr in self.wallet_addresses]
        
    def _update_account_details(self):
        """Now uses cached data instead of making RPC calls"""
        for provider in self:
            if not provider.wallet_address_value or not provider.wallet_addresses:
                provider.update({
                    'account_balance': 0,
                    'unlocked_balance': 0,
                    'account_index': 0
                })
                continue
            
            cached_data = next(
                (addr for addr in provider.wallet_addresses 
                 if addr['address'] == provider.wallet_address_value),
                None
            )
            
            if cached_data:
                provider.update({
                    'account_balance': cached_data['balance'],
                    'unlocked_balance': cached_data['unlocked_balance'],
                    'account_index': cached_data['account_index']
                })
            else:
                provider.update({
                    'account_balance': 0,
                    'unlocked_balance': 0,
                    'account_index': 0
                })

    def _get_wallet_addresses_selection(self):
        """Handle multiple providers by returning combined addresses"""
        addresses = []
        for provider in self:
            if provider.wallet_addresses:
                addresses.extend([
                    (addr['address'], addr['label']) 
                    for addr in provider.wallet_addresses
                ])
        return addresses

    def _inverse_wallet_address(self):
        """Store the selected address"""
        for provider in self:
            provider.wallet_address_value = provider.wallet_address
            if provider.wallet_address:
                cached = next(
                    (a for a in provider.wallet_addresses 
                     if a['address'] == provider.wallet_address),
                    None
                )
                if cached:
                    provider._update_account_from_cache(cached)

    @api.onchange('wallet_address')
    def _onchange_wallet_address(self):
        """Update balances when address changes"""
        if self.wallet_address:
            self._update_account_details()
