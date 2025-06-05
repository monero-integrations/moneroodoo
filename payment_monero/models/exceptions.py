# -*- coding: utf-8 -*-

from odoo.addons.queue_job.exception import RetryableJobError # type: ignore


class MoneroTransactionUpdateJobError(RetryableJobError):
    pass


class MoneroNoTransactionFoundError(RetryableJobError):
    pass


class MoneroNumConfirmationsNotMetError(RetryableJobError):
    pass


class MoneroWalletNotSynchronizedError(Exception):
    
    def __init__(self) -> None:
        super().__init__("Wallet is not synchronized")
