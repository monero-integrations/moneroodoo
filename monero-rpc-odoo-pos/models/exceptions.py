from requests.exceptions import SSLError
from odoo.addons.queue_job.exception import RetryableJobError


class MoneroTransactionUpdateJobError(RetryableJobError):
    pass


class MoneroPaymentMethodRPCUnauthorized(Exception):
    pass


class MoneroPaymentMethodRPCSSLError(SSLError):
    pass


class NoTXFound(RetryableJobError):
    pass


class NumConfirmationsNotMet(RetryableJobError):
    pass


class MoneroAddressReuse(Exception):
    pass
