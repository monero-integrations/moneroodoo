import logging
from monero.backends.jsonrpc import JSONRPCWallet, Unauthorized
from monero.wallet import Wallet
from odoo import api, fields, models
from requests.exceptions import SSLError
from .exceptions import MoneroPaymentAcquirerRPCUnauthorized, MoneroPaymentAcquirerRPCSSLError

_logger = logging.getLogger(__name__)

class MoneroPaymentProvider(models.Model):
    _inherit = "payment.provider"

    _sql_constraints = [
        ("unique_provider", "unique (provider)", "The provider must be unique."),
    ]

    provider = fields.Selection(
    selection=[
        ("paypal", "PayPal"),
        ("stripe", "Stripe"),
        ("bank", "Bank Transfer"),
        ("monero-rpc", "Monero"),
    ],
    string="Payment Provider",)
    
    is_cryptocurrency = fields.Boolean(
        string="Is Cryptocurrency", 
        default=True, 
        help="Indicates whether this is a cryptocurrency payment provider."
    )
    
    image_128 = fields.Binary(
        string="Logo",
        default=lambda self: self._get_default_image()
    )

    def _get_default_image(self):
        """Load Monero icon as base64."""
        image_path = tools.config['root_path'] + '/addons/monero-rpc-odoo/static/src/img/monero-symbol-480.png'
        try:
            with open(image_path, 'rb') as f:
                return base64.b64encode(f.read())
        except IOError:
            return False

    rpc_protocol = fields.Selection([("http", "HTTP"), ("https", "HTTPS")], default="http", string="RPC Protocol")
    monero_rpc_config_host = fields.Char(default="127.0.0.1", string="RPC Host", help="Monero RPC IP or hostname")
    monero_rpc_config_port = fields.Char(default="18082", string="RPC Port", help="Monero RPC listening port")
    monero_rpc_config_user = fields.Char(string="RPC User", help="User for Monero RPC authentication")
    monero_rpc_config_password = fields.Char(string="RPC Password", help="Password for Monero RPC authentication")
    
    num_confirmation_required = fields.Selection([
        ("0", "Low; 0-conf"),
        ("1", "Low-Med; 1-conf"),
        ("3", "Med; 3-conf"),
        ("6", "Med-High; 6-conf"),
        ("9", "High; 9-conf"),
        ("12", "High-Extreme; 12-conf"),
        ("15", "Extreme; 15-conf"),
    ], default="0", string="Security Level (Confirmations)", help="Required confirmations before marking transaction as done")

    def get_wallet(self):
        """Initialize and return a Monero wallet instance."""
        rpc_server = JSONRPCWallet(
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

    @api.onchange("rpc_protocol", "monero_rpc_config_host", "monero_rpc_config_port", "monero_rpc_config_user", "monero_rpc_config_password")
    def check_rpc_server_connection(self):
        """Check the Monero RPC connection when configuration changes."""
        _logger.info("Trying new Monero RPC Server configuration")
        try:
            wallet = self.get_wallet()
            warning = {"title": "Monero RPC Connection Test", "message": "Connection is successful"}
            _logger.info("Connection to Monero RPC successful")
        except MoneroPaymentAcquirerRPCUnauthorized:
            warning = {"title": "Monero RPC Connection Test", "message": "Invalid Monero RPC username or password"}
        except MoneroPaymentAcquirerRPCSSLError:
            warning = {"title": "Monero RPC Connection Test", "message": "Monero RPC TLS Error"}
        except Exception as e:
            warning = {"title": "Monero RPC Connection Test", "message": f"Monero RPC Connection Failed: {e.__class__.__name__}"}

        return {"warning": warning}

