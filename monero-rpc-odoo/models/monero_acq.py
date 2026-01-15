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
        selection_add=[("monero-rpc", "Monero")],
        ondelete={"monero-rpc": "set default"},
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

    def _process_transaction(self, transaction):
        """
        Process the Monero payment transaction.
        Creates token, subaddress, and sets up monitoring.
        """
        try:
            wallet = self.get_wallet()
            subaddress = wallet.new_address()[0]

            token = self.env['payment.token'].create({
                'name': subaddress,
                'partner_id': transaction.partner_id.id,
                'acquirer_id': self.id,
                'acquirer_ref': 'payment.payment_acquirer_monero_rpc',
                'active': False,
            })

            transaction.payment_token_id = token
            transaction.state = 'pending'

            # Set up cron for monitoring (copied from controller)
            num_conf_req = int(self.num_confirmation_required)
            if num_conf_req == 0:
                queue_channel = "monero_zeroconf_processing"
                interval_number = 15
            else:
                queue_channel = "monero_secure_processing"
                interval_number = 60

            action = self.env['ir.actions.server'].create({
                'name': f'Monero Transaction Processing ({queue_channel})',
                'model_id': self.env['ir.model']._get_id('sale.order'),
                'state': 'code',
                'code': f"""
record = env['sale.order'].browse({transaction.sale_order_ids[0].id})
record.process_transaction(
    env['payment.transaction'].browse({transaction.id}),
    env['payment.token'].browse({token.id}),
    {num_conf_req}
)
""",
            })

            self.env['ir.cron'].create({
                'name': f'Monero Processing ({queue_channel}) - {transaction.reference}',
                'ir_actions_server_id': action.id,
                'user_id': self.env.user.id,
                'active': True,
                'interval_number': interval_number,
                'interval_type': 'minutes',
            })

            return {'url': '/shop/payment/validate'}

        except Exception as e:
            _logger.error(f"Monero transaction processing failed: {e}")
            transaction.state = 'error'
            return {'url': '/shop/payment'}


class PaymentMethod(models.Model):
    _inherit = "payment.method"

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if 'code' in fields_list and not defaults.get('code'):
            defaults['code'] = 'xmr'
        return defaults
