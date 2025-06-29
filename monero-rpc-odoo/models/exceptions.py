from monero.backends.jsonrpc import Unauthorized
from requests.exceptions import SSLError
from odoo.addons.queue_job.exception import RetryableJobError


class MoneroPaymentAcquirerRPCUnauthorized(Unauthorized):
    pass


class MoneroPaymentAcquirerRPCSSLError(SSLError):
    pass


class NoTXFound(RetryableJobError):
    pass


class NumConfirmationsNotMet(RetryableJobError):
    pass


class MoneroAddressReuse(Exception):
    pass
