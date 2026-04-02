import logging
import secrets
import base64
import hashlib
import json
import os
import time
from decimal import Decimal
from io import BytesIO
from datetime import datetime, timedelta

import qrcode
import requests
import urllib.parse
from monero.wallet import Wallet
from monero.backends.jsonrpc import JSONRPCWallet
from monero.daemon import Daemon, JSONRPCDaemon
from monero.address import Address, SubAddress
from monero.exceptions import WrongAddress as InvalidAddress

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

class PaymentProviderMonero(models.Model):
    """Monero payment provider implementation for Odoo.

    This class extends the base payment.provider model to support Monero cryptocurrency
    payments through RPC communication with a Monero wallet and daemon. It handles
    payment creation, address generation, balance tracking, and exchange rate management.

    Attributes
    ----------
    _inherit : str
        Inherits from 'payment.provider' model

    Notes
    -----
    Key Features:
    - Monero wallet RPC integration
    - Subaddress generation for privacy
    - Exchange rate management
    - Payment status tracking
    - Automatic cron jobs for updates
    """

    _inherit = 'payment.provider'

    @api.model
    def _valid_field_parameter(self, field, name):
        return name == 'password' or super()._valid_field_parameter(field, name)

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
    rpc_password = fields.Char(string='RPC Password', password=True)
    wallet_file = fields.Char(string='Wallet File')
    wallet_password = fields.Char(string='Wallet Password', password=True)
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
        default={},
        help="Fallback exchange rates (e.g. {\"USD\": 150}) used when the live API is unavailable. "
             "Leave empty to force live rate fetching. Stale values here will silently produce wrong amounts."
    )

    wallet_addresses = fields.Json(
        string="Available Wallets",
        default=lambda self: [],
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
        try:
            from odoo.modules import module as odoo_module
            image_path = os.path.join(
                odoo_module.get_module_path('payment_monero_rpc'),
                'static', 'src', 'img', 'logo_chain.png'
            )
            with open(image_path, 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8')
        except IOError:
            return False

    image_128 = fields.Image(default=_get_default_monero_image)
    
    @api.model
    def _get_monero_provider(self):
        """Get the Monero payment provider singleton.

        Returns
        -------
        recordset
            The Monero payment provider record, or empty recordset if not found
        """
        return self.env['payment.provider'].search([('code', '=', 'monero_rpc')], limit=1)

    def _get_daemon(self):
        """Initialize and return Monero Daemon RPC client.

        Returns
        -------
        monero.daemon.Daemon
            Configured daemon client instance

        Raises
        ------
        UserError
            If connection to daemon fails
        """
        self.ensure_one()
        try:
            # Issue 45: use self directly — we are already the provider record
            parsed_url = urllib.parse.urlparse(self.daemon_rpc_url or '')
            host = parsed_url.hostname or "127.0.0.1"
            # Issue 46: 38081 is the stagenet daemon port; 18081 for mainnet
            port = parsed_url.port or 38081

            # Issue 44: use Daemon (imported from monero.daemon), not monero.daemon.Daemon
            daemon_rpc = Daemon(
                JSONRPCDaemon(
                    host=host,
                    port=port,
                    user=self.rpc_user or None,
                    password=self.rpc_password or None,
                    timeout=self.rpc_timeout or 180
                )
            )
            return daemon_rpc
        except Exception as e:
            _logger.error("Daemon connection failed: %s", str(e))
            raise UserError(_("Could not connect to Monero daemon. Please check your RPC settings."))

    def _get_wallet_client(self):
        """Initialize Monero wallet client.

        Returns
        -------
        monero.wallet.Wallet
            Configured wallet client instance

        Raises
        ------
        UserError
            If wallet file not found or connection fails
        """
        self.ensure_one()
        try:
            # Issue 47: use self — already the provider record, no DB search needed
            _logger.debug("RPC Wallet connecting: %s user=%s timeout=%s",
                          self.rpc_url, self.rpc_user, self.rpc_timeout)
            host = "127.0.0.1"
            port = 38082
            if self.rpc_url:
                parsed_url = urllib.parse.urlparse(self.rpc_url)
                host = parsed_url.hostname or "127.0.0.1"
                port = parsed_url.port or 38082

            # Issue 48: os.path.exists check is only valid when Odoo runs on the same
            # host as the wallet process. For remote wallet RPC setups it always fails.
            # Removed — the JSONRPCWallet connection itself will fail if the wallet is absent.

            wallet = Wallet(
                JSONRPCWallet(
                    host=host,
                    port=port,
                    user=self.rpc_user,
                    password=self.rpc_password,
                    timeout=self.rpc_timeout or 180)
            )
            return wallet
        except UserError:
            raise
        except Exception as e:
            _logger.error("Wallet connection failed: %s", str(e))
            raise UserError(_("Could not connect to Monero wallet. Please check your RPC settings.")) from e
        
    def _validate_address(self, addr_str, is_subaddress=True):
        """Validate a Monero address.

        Parameters
        ----------
        addr_str : str
            Address string to validate
        is_subaddress : bool, optional
            Whether to validate as subaddress, by default True

        Returns
        -------
        bool
            True if address is valid, False otherwise
        """
        try:
            if is_subaddress:
                SubAddress(addr_str)
            else:
                Address(addr_str)
            return True
        except (InvalidAddress, ValueError):
            return False
        
    @api.model
    def _cron_update_payment_provider(self):
        """Cron job to update payment provider data."""
        provider = self.env['payment.provider'].search([('code', '=', 'monero_rpc')], limit=1)
        if provider:
            provider.fetch_wallet_addresses()

    def _update_account_from_cache(self, cached_data):
        """Update account details from cached wallet data.

        Parameters
        ----------
        cached_data : dict
            Dictionary containing balance and account index data
        """
        self.write({
            'account_balance': cached_data.get('balance', 0),
            'unlocked_balance': cached_data.get('unlocked_balance', 0),
            'account_index': cached_data.get('account_index', 0)
        })

    def _create_monero_from_fiat_payment(self, order_ref, amount, currency, order_id):
        """Create a Monero payment from fiat amount.

        Parameters
        ----------
        order_ref : str
            Order reference string
        amount : float
            Fiat amount to convert
        currency : str or record
            Currency to convert from
        order_id : record or None
            Related sale order

        Returns
        -------
        recordset
            Created monero.payment record

        Raises
        ------
        UserError
            If exchange rate unavailable or payment creation fails
        """
        self.ensure_one()
        order_currency = currency.name if hasattr(currency, 'name') else currency
        rate = self.get_xmr_rate(order_currency)
        if not rate:
            raise UserError(_("Could not get exchange rate for %s") % currency)

        try:
            wallet = self._get_wallet_client()

            if self.use_subaddresses:
                label = f"Order_{order_ref}"
                subaddress = wallet.new_address(label=label)
                _logger.debug("New subaddress generated for order %s", order_ref)
                if not self._validate_address(subaddress[0], is_subaddress=True):
                    raise UserError(_("Generated invalid subaddress for current network"))

                payment_values = {
                    'payment_id': str(subaddress[1]),  # convert index to str
                    'address_seller': subaddress[0],
                    'is_subaddress': True,
                }
            else:
                payment_id = secrets.token_hex(8)  # 8-byte payment ID
                if not self.wallet_address_value:
                    raise UserError(_("No base wallet address configured for payment ID mode"))

                integrated_address = wallet.integrated_address(
                    payment_id=payment_id,
                    address=self.wallet_address_value
                )
                if not self._validate_address(integrated_address, is_subaddress=False):
                    raise UserError(_("Generated invalid integrated address"))

                payment_values = {
                    'payment_id': payment_id,
                    'address_seller': integrated_address,
                    'is_subaddress': False
                }

            payment = self.env['monero.payment'].sudo().create({
                **payment_values,
                'amount': float(Decimal(str(amount)) / Decimal(str(rate))),
                'exchange_rate': rate,
                'currency': 'XMR',
                'order_ref': order_ref,
                'state': 'pending',
                'expiration': fields.Datetime.add(fields.Datetime.now(), hours=24),
                'original_amount': amount,
                'original_currency': order_currency,
                **({'sale_order_id': order_id.id} if order_id else {})
            })
            # QR code is computed automatically via ORM dependency chain
            return payment

        except UserError:
            raise
        except Exception as e:
            _logger.error("Payment creation failed: %s", str(e), exc_info=True)
            raise UserError(_("Failed to create payment: %s") % str(e))

    @api.model
    def create_monero_from_fiat_payment(self, pos_reference, amount, currency_name, extra_data=None):
        """Public API to create Monero payment from fiat amount.

        Parameters
        ----------
        pos_reference : str
            POS or order reference
        amount : float
            Fiat amount
        currency_name : str
            Currency code
        extra_data : any, optional
            Additional payment data, by default None

        Returns
        -------
        dict
            Payment creation result
        """
        result = self._create_monero_from_fiat_payment(pos_reference, amount, currency_name, extra_data)
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

    def _generate_subaddress(self, label=None):
        """Generate a new subaddress.

        Parameters
        ----------
        label : str, optional
            Address label, by default None

        Returns
        -------
        dict
            Dictionary with address index and address string

        Raises
        ------
        UserError
            If address generation fails
        """
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
        """Generate an integrated address.

        Parameters
        ----------
        base_address : str
            Base Monero address
        payment_id : str
            Payment ID to integrate

        Returns
        -------
        str
            Generated integrated address
        """
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
        """Get current XMR exchange rate."""
        return self._fetch_xmr_rate(currency)

    def _compute_wallet_selection(self):
        """Compute selection options for wallet addresses.

        Returns
        -------
        list
            List of (value, label) tuples for selection field
        """
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

    @api.depends('wallet_address', 'wallet_addresses')
    def _compute_account_details(self):
        """Compute account balance details from cached wallet data.

        Reads from wallet_addresses cache populated by fetch_wallet_addresses().
        No live RPC call is made here — call fetch_wallet_addresses() explicitly
        to refresh.
        """
        for provider in self:
            cached = None
            if provider.wallet_address and provider.wallet_addresses:
                cached = next(
                    (a for a in provider.wallet_addresses
                     if a.get('address') == provider.wallet_address),
                    None
                )
            if cached:
                provider.account_balance = cached.get('balance', 0)
                provider.unlocked_balance = cached.get('unlocked_balance', 0)
                provider.account_index = cached.get('account_index', 0)
            else:
                provider.account_balance = 0
                provider.unlocked_balance = 0
                provider.account_index = 0

    def _get_account_index(self, address):
        """Get account index for an address.

        Parameters
        ----------
        address : str
            Monero address

        Returns
        -------
        int
            Account index, 0 if not found
        """
        try:
            wallet = self._get_wallet_client()
            return wallet.address_index(address)
        except Exception:
            return 0

    @api.model
    def _setup_monero_payment_method(self):
        """Create or update Monero payment method record.

        Returns
        -------
        recordset
            Payment method record
        """
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
        """Get compatible payment methods including Monero.

        Parameters
        ----------
        partner_id : int
            Partner ID
        currency_id : int, optional
            Currency ID, by default None
        **kwargs
            Additional arguments

        Returns
        -------
        recordset
            Compatible payment methods
        """
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

            payment_methods |= monero_method

        return payment_methods
        
    def get_manual_rate(self, currency):
        """Get manually configured exchange rate.

        Parameters
        ----------
        currency : str or record
            Currency to get rate for

        Returns
        -------
        float or None
            Manual rate if available, None otherwise
        """
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
    def _fetch_xmr_rate(self, currency='USD'):
        """Fetch current XMR exchange rate from API, with 60-second cache.

        Parameters
        ----------
        currency : str, optional
            Currency code, by default 'USD'

        Returns
        -------
        float or None
            Current exchange rate
        """
        currency = currency.upper()
        # Issue 54: cache the rate in ir.config_parameter with a TTL to avoid
        # hitting CoinGecko's rate limit (~30 req/min) on every payment creation.
        config = self.env['ir.config_parameter'].sudo()
        cache_key = f'monero.rate_cache.{currency}'
        ts_key = f'monero.rate_cache_ts.{currency}'
        now = time.time()
        cached_ts = float(config.get_param(ts_key, '0') or '0')
        if now - cached_ts < 60:
            cached = config.get_param(cache_key)
            if cached:
                return float(cached)

        provider = self if self._name == 'payment.provider' and self.ids else \
            self.env['payment.provider'].search([('code', '=', 'monero_rpc')], limit=1)

        try:
            response = requests.get(
                provider.exchange_rate_api,
                params={
                    'ids': 'monero',
                    'vs_currencies': currency.lower()},
                timeout=5
            )
            response.raise_for_status()
            data = response.json()
            rate = data.get('monero', {}).get(currency.lower())
            if rate:
                config.set_param(cache_key, str(rate))
                config.set_param(ts_key, str(now))
                return rate
            # Issue 55: warn explicitly when falling back to manual rates
            _logger.warning(
                "XMR rate API returned no data for %s — falling back to manual rates. "
                "Manual rates may be stale.", currency
            )
            return self.get_manual_rate(currency)
        except Exception as e:
            # Issue 55: log a clear warning so admins know rates are stale
            _logger.warning(
                "XMR rate fetch failed for %s (%s) — falling back to manual rates. "
                "Payments may use incorrect amounts if manual rates are stale.",
                currency, str(e)
            )
            return self.get_manual_rate(currency)

    # Keep old name as alias so existing cron XML records still work
    _cron_update_xmr_rates = _fetch_xmr_rate

    def fetch_wallet_addresses(self):
        """Fetch wallet addresses and balances.

        Returns
        -------
        bool
            True if successful, False otherwise

        Raises
        ------
        UserError
            If wallet operation fails
        """
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
                        'balance': balance.balance / 1_000_000_000_000,
                        'unlocked_balance': balance.unlocked_balance / 1_000_000_000_000,
                        'base_address': addr.address,
                    })

                if wallet_data:
                    provider.write({
                        'wallet_addresses': wallet_data,
                        'wallet_address': wallet_data[0]['address'],
                        'account_balance': wallet_data[0]['balance'],
                        'unlocked_balance': wallet_data[0]['unlocked_balance'],
                        'account_index': wallet_data[0]['account_index'],
                        'wallet_status': 'ready',
                    })
                else:
                    provider.write({'wallet_status': 'empty'})

                return True

            except Exception as e:
                _logger.error("Wallet operation failed: %s", str(e), exc_info=True)
                provider.write({'wallet_status': 'error'})
                raise UserError(str(e)) from e

    def _handle_fetch_error(self, provider):
        """Handle wallet fetch errors.

        Parameters
        ----------
        provider : recordset
            Payment provider record
        """
        provider.write({
            'wallet_addresses': [],
            'wallet_address': False,
            'wallet_address_value': False,
            'account_balance': 0,
            'unlocked_balance': 0,
            'account_index': 0
        })

    def _get_cached_wallet_selection(self):
        """Get wallet selection options from cache.

        Returns
        -------
        list
            List of (address, label) tuples
        """
        self.ensure_one()
        if not self.wallet_addresses:
            return []
        return [(addr['address'], addr['label']) for addr in self.wallet_addresses]
        
    def _update_account_details(self):
        """Update account details from cache."""
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
        """Get combined wallet addresses for all providers.

        Returns
        -------
        list
            List of (address, label) tuples
        """
        addresses = []
        for provider in self:
            if provider.wallet_addresses:
                addresses.extend([
                    (addr['address'], addr['label']) 
                    for addr in provider.wallet_addresses
                ])
        return addresses

    def _inverse_wallet_address(self):
        """Store selected wallet address and update account details."""
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
        """Handle wallet address change."""
        if self.wallet_address:
            self._update_account_details()
