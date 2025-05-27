import logging

from monero import MoneroRpcConnection, MoneroWallet, MoneroWalletFull, MoneroWalletRpc, MoneroNetworkType, MoneroWalletConfig, MoneroDaemonRpc, MoneroUtils

_logger = logging.getLogger(__name__)


class MoneroWalletManager:

    _wallet: MoneroWallet | None = None
    _FULL_WALLET_PATH: str = "monero_odoo_wallet"
    _FULL_WALLET_PASSWORD: str = ""
    _connection: MoneroRpcConnection | None = None

    def __init__(self) -> None:
        raise NotImplementedError("MoneroWalletManager is an abstract class")

    @classmethod
    def get_daemon_rpc(cls) -> MoneroDaemonRpc:
        if cls._connection is None:
            raise Exception(f"Connection not set")
        
        return MoneroDaemonRpc(cls._connection)

    @classmethod
    def get_daemon_height(cls) -> int:
        daemon = cls.get_daemon_rpc()

        return daemon.get_height()

    @classmethod
    def close_wallet(cls) -> None:
        if cls._wallet is None:
            return
        
        if cls._wallet.is_closed():
            cls._wallet = None
            return

        cls._wallet.close(True)
        cls._wallet = None

    @classmethod
    def get_wallet(cls) -> MoneroWallet:
        if cls._wallet is None or cls._wallet.is_closed():
            raise Exception("Wallet not loaded")

        return cls._wallet

    @classmethod
    def load_connection(cls, rpc_uri: str, rpc_username: str | None = None, rpc_password: str | None = None) -> MoneroRpcConnection:
        if cls._connection is not None:
            if cls._connection.uri == rpc_uri and cls._connection.username == rpc_username and cls._connection.password == rpc_password:
                return cls._connection
        
        cls._connection = MoneroRpcConnection(rpc_uri, rpc_username if rpc_username is not None else '', rpc_password if rpc_password is not None else '')
        return cls._connection

    @classmethod
    def check_connection(cls) -> None:
        if cls._connection is None:
            raise Exception("No RPC connection set")
        
        if not cls._connection.is_connected() and not cls._connection.check_connection():
            raise Exception(f"Could not connect to RPC uri {cls._connection.uri}")

    @classmethod
    def load_wallet_full(
        cls, 
        primary_address: str,
        private_view_key: str,
        network_type: MoneroNetworkType,
        rpc_uri: str, 
        rpc_username: str, 
        rpc_password: str
    ) -> MoneroWalletFull:
        
        if MoneroWalletFull.wallet_exists(cls._FULL_WALLET_PATH):
            wallet = MoneroWalletFull.open_wallet(cls._FULL_WALLET_PATH, cls._FULL_WALLET_PASSWORD, network_type)
            
            if wallet.get_primary_address() != primary_address:
                # devo cancellare in qualche modo il wallet salvato...
                raise NotImplementedError("Old deletion wallet not implemented")
            
            connection = cls.load_connection(rpc_uri, rpc_username, rpc_password)
            cls.check_connection()

            wallet.set_daemon_connection(connection)

            return wallet
        
        connection = cls.load_connection(rpc_uri, rpc_username, rpc_password)
        cls.check_connection()

        config = MoneroWalletConfig()
        config.primary_address = primary_address
        config.private_view_key = private_view_key
        config.path = cls._FULL_WALLET_PATH
        config.password = cls._FULL_WALLET_PASSWORD
        config.network_type = network_type
        # config.server = connection
        config.restore_height = cls.get_daemon_height()

        wallet = MoneroWalletFull.create_wallet(config)
        
        wallet.set_daemon_connection(connection)
        return wallet

    @classmethod
    def load_wallet_rpc(
        cls,
        primary_address: str,
        private_view_key: str,
        network_type: MoneroNetworkType,
        rpc_uri: str,
        rpc_username: str,
        rpc_password: str
    ) -> MoneroWalletRpc:
        
        connection = cls.load_connection(rpc_uri, rpc_username, rpc_password)
        wallet = MoneroWalletRpc(connection)
        config = MoneroWalletConfig()
        config.primary_address = primary_address
        config.private_view_key = private_view_key
        config.path = cls._FULL_WALLET_PATH
        config.network_type = network_type

        return wallet.open_wallet(config)

    @classmethod
    def check_load_wallet_params(cls, primary_address: str, private_view_key: str, network_type: MoneroNetworkType, rpc_uri: str, rpc_username: str, rpc_password: str) -> None:
        MoneroUtils.validate_address(primary_address, network_type)
        MoneroUtils.validate_private_view_key(private_view_key)

        if rpc_uri is None or rpc_uri == "":
            raise Exception("Empty rpc uri")

    @classmethod
    def load_wallet(
        cls, 
        wallet_type: str,
        primary_address: str,
        private_view_key: str, 
        network_type: MoneroNetworkType,
        rpc_uri: str, 
        rpc_username: str, 
        rpc_password: str
    ) -> MoneroWallet:
        cls.check_load_wallet_params(primary_address, private_view_key, network_type, rpc_uri, rpc_username, rpc_password)
        cls.close_wallet()
        if wallet_type.lower() == "full":
            cls._wallet = cls.load_wallet_full(primary_address, private_view_key, network_type, rpc_uri, rpc_username, rpc_password)
        elif wallet_type.lower() == "rpc":
            cls._wallet = cls.load_wallet_rpc(primary_address, private_view_key, network_type, rpc_uri, rpc_username, rpc_password)
        else:
            raise Exception("Invalid wallet type provided")
        
        _logger.warning(f"Starting wallet sync...")
        cls._wallet.start_syncing()
        _logger.warning(f"Started wallet syncing")

        return cls._wallet
    
    @classmethod
    def wallet_needs_reload(cls, wallet_type: str) -> bool:
        if wallet_type.lower() == "full" and not isinstance(cls._wallet, MoneroWalletFull):
            return True
        
        elif wallet_type.lower() == "rpc" and not isinstance(cls._wallet, MoneroWalletRpc):
            return True
        
        return False
    