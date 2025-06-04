# -*- coding: utf-8 -*-

import logging

from typing import override
from monero import (
    MoneroRpcConnection, MoneroWallet, MoneroWalletFull, MoneroWalletRpc, 
    MoneroNetworkType, MoneroWalletConfig, MoneroDaemonRpc, MoneroUtils, 
    MoneroWalletListener, MoneroWalletKeys, MoneroOutputWallet
)

_logger = logging.getLogger(__name__)

class MoneroWalletManagerListener(MoneroWalletListener):

    def __init__(self) -> None:
        MoneroWalletListener.__init__(self)
    
    @override
    def on_sync_progress(self, height: int, start_height: int, end_height: int, percent_done: float, message: str) -> None:
        _logger.info(f"Monero wallet sync progess {percent_done}% (height: {height}, start_height: {start_height}, end_height: {end_height})")

    @override
    def on_output_received(self, output: MoneroOutputWallet) -> None:
        _logger.info(f"Received output {output.stealth_public_key}, amount {output.amount}, account {output.account_index}, subaddress {output.subaddress_index}")

class MoneroWalletManager:

    _listener: MoneroWalletManagerListener = MoneroWalletManagerListener()
    _wallet: MoneroWallet | None = None
    _FULL_WALLET_PATH: str = "monero_odoo_wallet"
    _FULL_WALLET_PASSWORD: str = ""
    _connection: MoneroRpcConnection | None = None

    def __init__(self) -> None:
        raise NotImplementedError("MoneroWalletManager is an abstract class")

    @classmethod
    def validate_wallet_keys(cls, primary_address: str, view_key: str, nettype: MoneroNetworkType) -> None:
        try:
            config = MoneroWalletConfig()
            config.primary_address = primary_address
            config.private_view_key = view_key
            config.network_type = nettype
            MoneroWalletKeys.create_wallet_from_keys(config)
        except:
            raise Exception(f"The private view key doesn't belong to address {primary_address}")

    @classmethod
    def is_valid_wallet_keys(cls, primary_address: str, view_key: str, nettype: MoneroNetworkType) -> bool:
        try:
            cls.validate_wallet_keys(primary_address, view_key, nettype)
            return True
        except:
            return False

    @classmethod
    def get_wallet_path(cls, nettype: MoneroNetworkType) -> str:
        if nettype == MoneroNetworkType.MAINNET:
            return f"{cls._FULL_WALLET_PATH}_mainnet"
        elif nettype == MoneroNetworkType.TESTNET:
            return f"{cls._FULL_WALLET_PATH}_testnet"
        else:
            return f"{cls._FULL_WALLET_PATH}_stagenet"

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
        account_lookahead: int,
        network_type: MoneroNetworkType,
        rpc_uri: str, 
        rpc_username: str, 
        rpc_password: str
    ) -> MoneroWalletFull:
        wallet_path = cls.get_wallet_path(network_type)
        if MoneroWalletFull.wallet_exists(wallet_path):
            wallet = MoneroWalletFull.open_wallet(wallet_path, cls._FULL_WALLET_PASSWORD, network_type)
            
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
        config.path = cls.get_wallet_path(network_type)
        config.password = cls._FULL_WALLET_PASSWORD
        config.network_type = network_type
        if account_lookahead > 0:
            config.account_lookahead = account_lookahead
            config.subaddress_lookahead = 10
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
        account_lookahead: int,
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
        config.path = cls.get_wallet_path(network_type)
        config.network_type = network_type
        if account_lookahead > 0:
            config.account_lookahead = account_lookahead
            config.subaddress_lookahead = 10

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
        account_lookahead: int,
        network_type: MoneroNetworkType,
        rpc_uri: str, 
        rpc_username: str, 
        rpc_password: str
    ) -> MoneroWallet:
        cls.check_load_wallet_params(primary_address, private_view_key, network_type, rpc_uri, rpc_username, rpc_password)
        cls.close_wallet()
        if wallet_type.lower() == "full":
            cls._wallet = cls.load_wallet_full(primary_address, private_view_key, account_lookahead, network_type, rpc_uri, rpc_username, rpc_password)
        elif wallet_type.lower() == "rpc":
            cls._wallet = cls.load_wallet_rpc(primary_address, private_view_key, account_lookahead, network_type, rpc_uri, rpc_username, rpc_password)
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
    