# -*- coding: utf-8 -*-

from typing_extensions import override

import logging

from odoo import api, fields
from odoo.addons.payment.models import payment_acquirer

from monero import MoneroWallet, MoneroSubaddress, MoneroTransferQuery, MoneroError, MoneroTxQuery, MoneroTransfer, MoneroIncomingTransfer

_logger = logging.getLogger(__name__)


class MoneroPaymentAcquirer(payment_acquirer.PaymentAcquirer):
    """
    Inherits from payment.acquirer
    Custom fields added: is_cryptocurrency, environment, type
    """

    _inherit = "payment.acquirer"
    _recent_transactions = []

    # region Missing
    
    id: str

    # endregion

    # region Fields

    provider = fields.Selection(
        selection_add=[("monero-rpc", "Monero")], ondelete={"monero-rpc": "set default"}
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

    # endregion

    # region Overrides

    @override
    def _get_default_payment_method_id(self):
        self.ensure_one()
        if self.provider != 'monero-rpc':
            return super()._get_default_payment_method_id()
        _logger.warning(self.env)
        _logger.warning(dir(self.env))
        return self.env.ref('monero-rpc-odoo.payment_method_monero').id

    # endregion

    # region Methods

    def get_wallet(self) -> MoneroWallet:
        raise NotImplementedError()

    def get_account_index(self) -> int:
        raise NotImplementedError()

    def create_subaddress(self, tag: str = '') -> MoneroSubaddress:
        wallet = self.get_wallet()
        account_index = self.get_account_index()
        return wallet.create_subaddress(account_index, tag)

    def get_num_confirmations_required(self) -> int:
        return int(self.num_confirmation_required) # type: ignore

    def get_incoming_unconfirmed_transfers(self, address: str) -> list[MoneroIncomingTransfer]:
        result: list[MoneroIncomingTransfer] = []
        wallet = self.get_wallet()
        index = wallet.get_address_index(address)
        if index.index is None:
            raise MoneroError("Could not get address index")
        
        query = MoneroTransferQuery()
        query.account_index = index.account_index
        query.subaddress_indices = [index.index]
        
        query.tx_query = MoneroTxQuery()
        query.tx_query.is_incoming = True

        transfers: list[MoneroTransfer] = wallet.get_transfers(query)

        for transfer in transfers:
            if isinstance(transfer, MoneroIncomingTransfer):
                result.append(transfer)

        return result

    # endregion

    # region API

    @api.onchange(
        "rpc_protocol",
        "monero_rpc_config_host",
        "monero_rpc_config_port",
        "monero_rpc_config_user",
        "monero_rpc_config_password",
    )
    def check_rpc_server_connection(self):
        _logger.info("Trying new Monero RPC Server configuration")
        wallet: MoneroWallet | None = None
        message: str = ""
        try:
            wallet = self.get_wallet()
        except Exception as e:
            message = (
                f"Monero RPC Connection Failed or other error: {e.__class__.__name__}"
            )
            pass

        title = "Monero RPC Connection Test"
        if wallet is not None:
            _logger.info("Connection to Monero RPC successful")
            warning = {"title": title, "message": "Connection is successful"}
        else:
            _logger.info(message)
            warning = {"title": title, "message": f"{message}"}

        return {"warning": warning}

    # endregion