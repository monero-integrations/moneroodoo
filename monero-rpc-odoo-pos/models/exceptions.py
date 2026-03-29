from monero.backends.jsonrpc import Unauthorized
from requests.exceptions import SSLError


class MoneroPaymentMethodRPCUnauthorized(Unauthorized):
    pass


class MoneroPaymentMethodRPCSSLError(SSLError):
    pass


class NoTXFound(Exception):
    """Raised when no transaction is found; cron will retry automatically."""
    pass


class NumConfirmationsNotMet(Exception):
    """Raised when confirmations are insufficient; cron will retry automatically."""
    pass


class MoneroAddressReuse(Exception):
    pass
