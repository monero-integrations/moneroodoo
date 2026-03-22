import logging

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


class MoneroPaymentTransaction(models.Model):
    """
    Inherits from payment.transaction to implement the Monero-specific
    redirect flow for Odoo 19.
    """

    _inherit = "payment.transaction"

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

        # Store the subaddress as the provider_reference on the transaction.
        # We do NOT use payment.token here — tokens are for saved payment methods
        # (credit cards etc.). A Monero subaddress is a one-time-use address and
        # should never be stored as a reusable token.
        self.sudo().write({'provider_reference': str(subaddress)})

        # Set transaction to pending state
        self._set_pending()

        # Set up cron job for payment polling
        num_conf_req = int(provider.num_confirmation_required)
        if num_conf_req == 0:
            queue_channel = "monero_zeroconf_processing"
            interval_number = 30  # Poll every 30 seconds for zero-conf
        else:
            queue_channel = "monero_secure_processing"
            interval_number = 60  # Poll every 60 seconds for confirmed

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
            'interval_number': interval_number,
            'interval_type': 'seconds',
        })

        # Trigger immediately for first check
        cron._trigger()

        _logger.info(
            f"Monero cron job created for transaction {self.reference}, "
            f"polling every {interval_number} seconds"
        )

        return {
            'api_url': '/payment/status',
            'subaddress': str(subaddress),
            'amount': self.amount,
            'currency': self.currency_id.name,
            'reference': self.reference,
        }
