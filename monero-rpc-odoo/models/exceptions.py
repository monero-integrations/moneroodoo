from monero.backends.jsonrpc import Unauthorized
from requests.exceptions import SSLError


class MoneroPaymentAcquirerRPCUnauthorized(Unauthorized):
    pass


class MoneroPaymentAcquirerRPCSSLError(SSLError):
    pass
