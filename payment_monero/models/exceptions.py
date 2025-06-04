# -*- coding: utf-8 -*-

from odoo.addons.queue_job.exception import RetryableJobError # type: ignore


class MoneroTransactionUpdateJobError(RetryableJobError):
    pass


class MoneroNoTransactionFoundError(RetryableJobError):
    pass


class MoneroNumConfirmationsNotMetError(RetryableJobError):
    pass
