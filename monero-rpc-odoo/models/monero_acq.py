# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

from monero.wallet import Wallet
from monero.backends.jsonrpc import JSONRPCWallet
from monero.backends.jsonrpc import Unauthorized
from requests.exceptions import SSLError

_logger = logging.getLogger(__name__)


class MoneroPaymentAcquirer(models.Model):
    """
    Inherits from payment.acquirer
    Custom fields added: is_cryptocurrency, environment, type
    """

    _inherit = "payment.acquirer"
    _recent_transactions = []

    @api.onchange('rpc_protocol', 'monero_rpc_config_host', 'monero_rpc_config_port', 'monero_rpc_config_path',
                  'monero_rpc_config_user', 'monero_rpc_config_password')
    def update_rpc_server(self):
        _logger.info("Trying new Monero RPC Server configuration")
        connection = False
        rpc_server: JSONRPCWallet = JSONRPCWallet(
                protocol=self.rpc_protocol,
                host=self.monero_rpc_config_host,
                port=self.monero_rpc_config_port,
                path=self.monero_rpc_config_path,
                user=self.monero_rpc_config_user,
                password=self.monero_rpc_config_password,
            )
        wallet = None
        try:
            wallet = Wallet(rpc_server)
        except Unauthorized as ue:
            message = "Invalid Monero RPC user name or password"
            pass
        except SSLError as se:
            message = "Monero RPC TLS Error"
            pass
        except Exception as e:
            message = f"Monero RPC Connection Failed or other error: {e.__class__.__name__}"
            pass

        if type(wallet) is Wallet:
            connection = True
            self.env["ir.config_parameter"].set_param("monero_rpc_server", rpc_server)
            self.env["ir.config_parameter"].set_param("monero_wallet", wallet)

        title = 'Monero RPC Connection Test'
        if connection:
            _logger.info('Connection to Monero RPC successful')
            warning = {
                'title': title,
                'message': 'Connection is successful'
            }
        else:
            warning = {
                'title': title,
                'message': f'{message}'
            }

        return {'warning': warning}

    provider = fields.Selection(
        selection_add=[("monero-rpc", "Monero")],
        ondelete={"monero-rpc": "set default"}
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
        [("http", "HTTP"), ("https", "HTTPS")],
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
        default="18082"
    )
    monero_rpc_config_path = fields.Char(
        string="RPC Path",
        help="The path of the Monero RPC",
        default="/json_rpc"
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
