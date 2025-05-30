from odoo.addons.queue_job.exception import RetryableJobError


class MoneroTransactionUpdateJobError(RetryableJobError):
    pass


class MoneroNoTransactionFoundError(RetryableJobError):
    pass


class MoneroNumConfirmationsNotMetError(RetryableJobError):
    pass
