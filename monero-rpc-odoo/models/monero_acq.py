import logging
from datetime import date as date_type

import requests as http_requests
from monero.backends.jsonrpc import JSONRPCWallet, Unauthorized
from monero.wallet import Wallet
from odoo import api, fields, models
from requests.exceptions import SSLError
from .exceptions import (
    MoneroPaymentAcquirerRPCUnauthorized,
    MoneroPaymentAcquirerRPCSSLError,
)

_logger = logging.getLogger(__name__)


class MoneroPaymentAcquirer(models.Model):
    """
    Inherits from payment.provider
    Custom fields added: is_cryptocurrency, environment, type
    """

    _inherit = "payment.provider"
    _recent_transactions = []

    def get_wallet(self):
        rpc_server: JSONRPCWallet = JSONRPCWallet(
            protocol=self.rpc_protocol,
            host=self.monero_rpc_config_host,
            port=self.monero_rpc_config_port,
            user=self.monero_rpc_config_user,
            password=self.monero_rpc_config_password,
        )
        try:
            wallet = Wallet(rpc_server)
        except Unauthorized:
            raise MoneroPaymentAcquirerRPCUnauthorized
        except SSLError:
            raise MoneroPaymentAcquirerRPCSSLError
        except Exception as e:
            _logger.critical("Monero RPC Error", exc_info=True)
            raise e

        return wallet

    @api.onchange(
        "rpc_protocol",
        "monero_rpc_config_host",
        "monero_rpc_config_port",
        "monero_rpc_config_user",
        "monero_rpc_config_password",
    )
    def check_rpc_server_connection(self):
        _logger.info("Trying new Monero RPC Server configuration")
        wallet = None
        try:
            wallet = self.get_wallet()
        except MoneroPaymentAcquirerRPCUnauthorized:
            message = "Invalid Monero RPC user name or password"
            pass
        except MoneroPaymentAcquirerRPCSSLError:
            message = "Monero RPC TLS Error"
            pass
        except Exception as e:
            message = (
                f"Monero RPC Connection Failed or other error: {e.__class__.__name__}"
            )
            pass

        title = "Monero RPC Connection Test"
        if type(wallet) is Wallet:
            _logger.info("Connection to Monero RPC successful")
            warning = {"title": title, "message": "Connection is successful"}
        else:
            _logger.info(message)
            warning = {"title": title, "message": f"{message}"}

        return {"warning": warning}

    code = fields.Selection(
        selection_add=[("monero_rpc", "Monero")],
        ondelete={"monero_rpc": "set default"},
    )

    is_cryptocurrency = fields.Boolean("Cryptocurrency?", default=False)
    # not used right now, could be used to update price data?
    type = fields.Selection(
        [("xmr", "XMR")],
        "none",
        default="xmr",
        required=True,
        help="Monero: A Private Digital Currency",
    )

    rpc_protocol = fields.Selection(
        [
            ("http", "HTTP"),
            ("https", "HTTPS"),
        ],
        "RPC Protocol",
        default="http",
    )
    monero_rpc_config_host = fields.Char(
        string="RPC Host",
        help="The ip address or host name of the Monero RPC",
        default="127.0.0.1",
    )
    monero_rpc_config_port = fields.Char(
        string="RPC Port",
        help="The port the Monero RPC is listening on",
        default="18082",
    )
    monero_rpc_config_user = fields.Char(
        string="RPC User",
        help="The user to authenticate with the Monero RPC",
        default=None,
    )
    monero_rpc_config_password = fields.Char(
        string="RPC Password",
        help="The password to authenticate with the Monero RPC",
        default=None,
    )
    num_confirmation_required = fields.Selection(
        [
            ("0", "Low; 0-conf"),
            ("1", "Low-Med; 1-conf"),
            ("3", "Med; 3-conf"),
            ("6", "Med-High; 6-conf"),
            ("9", "High; 9-conf"),
            ("12", "High-Extreme; 12-conf"),
            ("15", "Extreme; 15-conf"),
        ],
        "Security Level (Confirmations)",
        default="0",
        help="Required Number of confirmations "
        "before an order's transactions is set to done",
    )

    def _get_default_payment_method_codes(self):
        """Return the default payment method codes for Monero provider."""
        self.ensure_one()
        if self.code == 'monero_rpc':
            return {'monero_rpc'}
        return super()._get_default_payment_method_codes()

    @api.model
    def update_xmr_rate(self):
        """
        Fetch the current XMR/USD rate from CoinGecko and update the XMR
        currency rate in Odoo. Called by the scheduled cron every 15 minutes.
        """
        try:
            resp = http_requests.get(
                'https://api.coingecko.com/api/v3/simple/price',
                params={'ids': 'monero', 'vs_currencies': 'usd'},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            xmr_usd = data['monero']['usd']  # e.g. 150.0 means 1 XMR = $150
        except Exception as e:
            _logger.warning(f"Monero rate update failed: {e}")
            return

        xmr_currency = self.env['res.currency'].search([('name', '=', 'XMR')], limit=1)
        if not xmr_currency:
            _logger.warning("XMR currency not found in Odoo. Cannot update rate.")
            return

        # Odoo stores rates as: 1 unit of company currency = rate units of this currency
        # If company currency is USD and 1 XMR = $150, then rate = 1/150
        # But Odoo's rate field means: 1 USD = rate XMR, so rate = 1/xmr_usd
        # Actually in Odoo 17+: rate = (1 / xmr_usd) means 1 USD buys 1/150 XMR
        # We store: how many XMR per 1 USD = 1/xmr_usd
        rate = 1.0 / xmr_usd

        # Update or create today's rate
        today = date_type.today()
        existing = self.env['res.currency.rate'].search([
            ('currency_id', '=', xmr_currency.id),
            ('name', '=', today),
        ], limit=1)

        if existing:
            existing.write({'rate': rate})
        else:
            self.env['res.currency.rate'].create({
                'currency_id': xmr_currency.id,
                'name': today,
                'rate': rate,
            })

        _logger.info(f"XMR rate updated: 1 XMR = ${xmr_usd} USD (rate={rate:.8f})")


class MoneroPaymentTransaction(models.Model):
    """
    Inherits from payment.transaction to implement the Monero-specific
    redirect flow for Odoo 19.
    """

    _inherit = "payment.transaction"

    monero_amount_xmr = fields.Float(
        string="Amount in XMR",
        digits=(16, 12),
        help="The exact XMR amount the buyer must send, converted at checkout time.",
    )
    monero_amount_original = fields.Float(
        string="Original Amount (before XMR conversion)",
        digits=(16, 2),
        help="The order amount in the original currency before converting to XMR.",
    )
    monero_currency_original = fields.Char(
        string="Original Currency",
        help="The original currency code before converting to XMR (e.g. USD).",
    )

    def _get_specific_rendering_values(self, processing_values):
        """
        Override to generate a Monero subaddress, create a payment token,
        and set up the cron job for payment polling.

        Called by _get_processing_values() when operation='online_redirect'
        and a redirect_form_view_id is set on the provider.

        :param dict processing_values: The generic processing values.
        :return: Dict with monero-specific rendering values for the redirect form.
        :rtype: dict
        """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'monero_rpc':
            return res

        provider = self.provider_id

        # Generate a fresh subaddress via Monero RPC
        try:
            wallet = provider.get_wallet()
            subaddress = wallet.new_address()[0]
            _logger.info(
                f"Generated Monero subaddress for transaction {self.reference}: {subaddress}"
            )
        except MoneroPaymentAcquirerRPCUnauthorized:
            _logger.error("Monero RPC: authentication failed")
            self._set_error("Monero RPC authentication failed")
            return res
        except MoneroPaymentAcquirerRPCSSLError:
            _logger.error("Monero RPC: SSL error")
            self._set_error("Monero RPC SSL error")
            return res
        except Exception as e:
            _logger.error(f"Monero RPC error: {e.__class__.__name__}: {e}")
            self._set_error(f"Monero RPC error: {e.__class__.__name__}")
            return res

        # Fetch live XMR/USD price from CoinGecko at the exact moment of checkout.
        # This gives the buyer the most accurate amount to send.
        order_currency = self.currency_id
        original_amount = self.amount
        xmr_amount = original_amount  # fallback: use original if conversion fails

        try:
            rate_resp = http_requests.get(
                'https://api.coingecko.com/api/v3/simple/price',
                params={'ids': 'monero', 'vs_currencies': order_currency.name.lower()},
                timeout=10,
            )
            rate_resp.raise_for_status()
            rate_data = rate_resp.json()
            xmr_price = rate_data.get('monero', {}).get(order_currency.name.lower())
            if xmr_price and xmr_price > 0:
                xmr_amount = original_amount / xmr_price
                _logger.info(
                    f"Live rate: 1 XMR = {xmr_price} {order_currency.name}. "
                    f"Converted {original_amount} {order_currency.name} → "
                    f"{xmr_amount:.12f} XMR for transaction {self.reference}"
                )
            else:
                _logger.warning(
                    f"CoinGecko did not return a rate for XMR/{order_currency.name}. "
                    f"Falling back to Odoo currency rate."
                )
                xmr_currency = self.env['res.currency'].search([('name', '=', 'XMR')], limit=1)
                if xmr_currency and order_currency.name != 'XMR':
                    xmr_amount = order_currency._convert(
                        original_amount, xmr_currency,
                        self.company_id or self.env.company, date_type.today(),
                    )
        except Exception as e:
            _logger.warning(
                f"Live XMR rate fetch failed for {self.reference}: {e}. "
                f"Falling back to Odoo currency rate."
            )
            xmr_currency = self.env['res.currency'].search([('name', '=', 'XMR')], limit=1)
            if xmr_currency and order_currency and order_currency.name != 'XMR':
                try:
                    xmr_amount = order_currency._convert(
                        original_amount, xmr_currency,
                        self.company_id or self.env.company, date_type.today(),
                    )
                except Exception:
                    pass  # keep xmr_amount = original_amount as last resort

        # Store the subaddress and XMR amount.
        # IMPORTANT: we do NOT overwrite tx.amount — Odoo uses it to validate
        # the payment against the sale order total. We store the XMR amount
        # in monero_amount_xmr for display and wallet comparison.
        self.sudo().write({
            'provider_reference': str(subaddress),
            'monero_amount_xmr': xmr_amount,
            'monero_amount_original': original_amount,
            'monero_currency_original': order_currency.name if order_currency else 'USD',
        })

        # Set transaction to pending state
        self._set_pending()

        # Set up cron job for payment polling
        num_conf_req = int(provider.num_confirmation_required)
        if num_conf_req == 0:
            queue_channel = "monero_zeroconf_processing"
        else:
            queue_channel = "monero_secure_processing"

        # Get the linked sale order (if any)
        sale_order_id = 0
        if hasattr(self, 'sale_order_ids') and self.sale_order_ids:
            sale_order_id = self.sale_order_ids[0].id

        action = self.env['ir.actions.server'].sudo().create({
            'name': f'Monero TX Processing ({queue_channel}) - {self.reference}',
            'model_id': self.env['ir.model']._get_id('sale.order'),
            'state': 'code',
            'code': (
                f"record = env['sale.order'].browse({sale_order_id})\n"
                f"record.process_transaction(\n"
                f"    env['payment.transaction'].browse({self.id}),\n"
                f"    {num_conf_req}\n"
                f")"
            ),
        })

        cron = self.env['ir.cron'].sudo().create({
            'name': f'Monero Processing ({queue_channel}) - {self.reference}',
            'ir_actions_server_id': action.id,
            'user_id': self.env.ref('base.user_root').id,
            'active': True,
            'interval_number': 1,
            'interval_type': 'minutes',
        })

        # Trigger immediately for first check
        cron._trigger()

        _logger.info(
            f"Monero cron job created for transaction {self.reference}, polling every 1 minute"
        )

        return {
            'api_url': '/payment/status',
            'subaddress': str(subaddress),
            'amount': xmr_amount,
            'currency': 'XMR',
            'reference': self.reference,
        }

    def _post_process(self):
        """
        Override to skip Odoo's default accounting journal entry creation.

        Odoo's /payment/status/poll endpoint calls _post_process() automatically
        when transaction.state == 'done'. The default implementation tries to
        create an account.payment record which requires a payment method line
        on the journal. For Monero (crypto), we skip that and just confirm
        the sale order directly.
        """
        if self.provider_code != 'monero_rpc':
            return super()._post_process()

        # Confirm the linked sale order(s) if not already confirmed
        for order in self.sale_order_ids:
            if order.state in ('draft', 'sent'):
                order.action_confirm()
                _logger.info(
                    f"Monero _post_process: confirmed sale order {order.id} "
                    f"for transaction {self.reference}"
                )
