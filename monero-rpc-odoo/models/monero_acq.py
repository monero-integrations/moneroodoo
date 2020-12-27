# -*- coding: utf-8 -*-
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class MoneroPaymentAcquirer(models.Model):
    """
    Inherits from payment.acquirer
    Custom fields added: is_cryptocurrency, environment, type
    """

    _inherit = "payment.acquirer"
    _recent_transactions = []

    provider = fields.Selection(
        selection_add=[("monero", "Monero")],
        ondelete={"monero": "set default"}
    )

    def _get_providers(self):
        providers = super(MoneroPaymentAcquirer, self)._get_providers()
        providers.append(["monero", "Monero"])
        return providers

    is_cryptocurrency = fields.Boolean("Cryptocurrency?", default=False)
    environment = fields.Selection(
        [("stage", "Stagenet"), ("test", "Testnet"), ("main", "Mainnet")],
        default="test",
    )
    # not used right now, could be used to update price data?
    type = fields.Selection(
        [("xmr", "XMR")],
        "none",
        default="xmr",
        required=True,
        help="Monero: A Private Digital Currency",
    )

    monero_rpc_config_protocol = fields.Selection(
        [("http", "HTTP"), ("https", "HTTPS")], default="http"
    )
    monero_rpc_config_host = fields.Char(
        string="RPC Host",
        help="The ip address or host name of the Monero RPC",
        default="127.0.0.1",
    )
    monero_rpc_config_port = fields.Integer(
        string="RPC Port",
        help="The port the Monero RPC is listening on",
        default=18082
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
