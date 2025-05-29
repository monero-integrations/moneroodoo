from requests.exceptions import SSLError
from odoo.addons.queue_job.exception import RetryableJobError


class MoneroPaymentAcquirerRPCUnauthorized(Exception):
    pass


class MoneroPaymentAcquirerRPCSSLError(SSLError):
    pass


class MoneroTransactionUpdateJobError(RetryableJobError):
    pass

class NoTXFound(RetryableJobError):
    pass


class NumConfirmationsNotMet(RetryableJobError):
    pass


class MoneroAddressReuse(Exception):
    pass
