import logging

from odoo import api, fields
from odoo.addons.point_of_sale.models import pos_payment_method

from monero import (
    MoneroWallet, MoneroIncomingTransfer, MoneroNetworkType, MoneroSubaddress,
    MoneroError, MoneroTransferQuery, MoneroTxQuery, MoneroTransfer,
    MoneroRpcConnection
)

from ..utils import MoneroWalletManager

_logger = logging.getLogger(__name__)

class MoneroPosPaymentMethod(pos_payment_method.PosPaymentMethod):
    """
    Inherits from pos.payment.method
    Custom fields added: is_cryptocurrency, environment, type
    """

    _inherit = "pos.payment.method"

    # region Private Methods

    def _get_payment_terminal_selection(self):
        return super(MoneroPosPaymentMethod, self)._get_payment_terminal_selection() + [
            ("monero", "Monero")
        ]

    # endregion

    # region Methods

    def get_wallet(self) -> MoneroWallet:
        try: 
            return MoneroWalletManager.get_wallet()
        except:
            self.load_wallet()
            return MoneroWalletManager.get_wallet()

    def get_account_index(self) -> int:
        return int(self.account_index) # type: ignore

    def get_wallet_type(self) -> str:
        return str(self.wallet_type)
    
    def get_rpc_uri(self) -> str:
        return str(self.rpc_uri)

    def get_rpc_username(self) -> str:
        return str(self.rpc_username)
    
    def get_rpc_password(self) -> str:
        return str(self.rpc_password)
    
    def get_network_type(self) -> MoneroNetworkType:
        nettype = str(self.network_type)
        if nettype == "mainnet":
            return MoneroNetworkType.MAINNET
        elif nettype == "stagenet":
            return MoneroNetworkType.STAGENET
        else:
            return MoneroNetworkType.TESTNET

    def get_primary_address(self) -> str:
        return str(self.wallet_primary_address)

    def get_private_view_key(self) -> str:
        return str(self.wallet_private_view_key)

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

    def load_wallet(self) -> MoneroWallet:
        MoneroWalletManager.load_connection(self.get_rpc_uri(), self.get_rpc_username(), self.get_rpc_password())
        MoneroWalletManager.check_connection()

        if not MoneroWalletManager.wallet_needs_reload(self.get_wallet_type()):
            return MoneroWalletManager.get_wallet()
        
        return MoneroWalletManager.load_wallet(
            self.get_wallet_type(),
            self.get_primary_address(),
            self.get_private_view_key(),
            self.get_account_index(),
            self.get_network_type(),
            self.get_rpc_uri(),
            self.get_rpc_username(),
            self.get_rpc_password()
        )

    # endregion

    # region API

    @api.onchange(
        "rpc_uri",
        "rpc_username",
        "rpc_password",
    )
    def check_rpc_server_connection(self):
        _logger.info("Trying new Monero RPC Server configuration")
        connection: MoneroRpcConnection | None = None
        message: str = ""
        try:
            connection = MoneroWalletManager.load_connection(self.get_rpc_uri(), self.get_rpc_username(), self.get_rpc_password())
            MoneroWalletManager.check_connection()
        except Exception as e:
            if connection is not None:
                message = f"Connection to Monero RPC {connection.uri} failed: {str(e)}"
            else:
                message = f"Connection to Monero RPC failed: {str(e)}"
            pass

        title = "Monero RPC Connection Test"
        if connection is not None and connection.is_connected():
            _logger.info(f"Connection to Monero RPC {connection.uri} successful")
            warning = {"title": title, "message": f"Connection to Monero RPC {connection.uri} successful"}
        else:
            _logger.info(message)
            warning = {"title": title, "message": f"{message}"}

        return { "warning": warning }

    # endregion

    # region Odoo Fields

    is_cryptocurrency = fields.Boolean("Cryptocurrency?", default=False)
    # not used right now, could be used to update price data?
    type = fields.Selection(
        [("xmr", "XMR")],
        "none",
        default="xmr",
        required=True,
        help="Monero: A Private Digital Currency",
    )

    wallet_type = fields.Selection(
        [
            ("full", "Full"),
            ("rpc", "RPC"),
        ],
        "Wallet Type",
        default="full",
    )
    wallet_primary_address = fields.Char(
        string="Primary Address",
        help="Wallet primary address, also known as standard address"       
    )
    wallet_private_view_key = fields.Char(
        string="Private View Key",
        help="Wallet private view key"
    )
    network_type = fields.Selection(
        [
            ("mainnet", "MAINNET"),
            ("testnet", "TESTNET"),
            ("stagenet", "STAGENET")
        ],
        "Network Type",
        default="mainnet",
    )
    account_index = fields.Integer(
        string="Account Index",
        help="The wallet's account index to use",
        default=0
    )
    rpc_uri = fields.Char(
        string="RPC Uri",
        help="The uri of the Monero RPC",
        default="http://127.0.0.1:18081/",
    )
    rpc_username = fields.Char(
        string="RPC Username",
        help="The user to authenticate with the Monero RPC",
        default=None,
    )
    rpc_password = fields.Char(
        string="RPC Password",
        help="The password to authenticate with the Monero RPC",
        default=None,
    )
    num_confirmation_required = fields.Selection(
        [
            ("0", "0-conf"),
            ("1", "1-conf"),
            ("3", "3-conf"),
            ("6", "6-conf"),
            ("9", "9-conf"),
            ("12", "12-conf"),
            ("15", "15-conf"),
        ],
        "Required Confirmations",
        default="0",
        help="Required Number of confirmations "
        "before an order's transactions is set to done",
    )

    #endregion
