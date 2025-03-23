import logging
from odoo import http
from odoo.http import request
from odoo.exceptions import ValidationError
from monero.wallet import Wallet
from monero.backends.jsonrpc import Unauthorized
from requests.exceptions import SSLError
from odoo.addons.queue_job.exception import RetryableJobError

_logger = logging.getLogger(__name__)

class MoneroController(http.Controller):
    @http.route("/pos/monero/get_address", type="json", auth="public", website=True, methods=["POST"])
    def get_address(self, **kwargs):
        payment_method = request.env["pos.payment.method"].sudo().browse(int(kwargs.get("payment_method_id")))
        if payment_method is not None:
            try:
                wallet = payment_method.get_wallet()
            except Unauthorized:
                _logger.error("USER IMPACT: Monero POS Payment Method can't authenticate with RPC due to user name or password")
                raise ValidationError("Current technical issues prevent Monero from being accepted, choose another payment method")
            except SSLError:
                _logger.error("USER IMPACT: Monero POS Payment Method experienced an SSL Error with RPC")
                raise ValidationError("Current technical issues prevent Monero from being accepted, choose another payment method")
            except Exception as e:
                _logger.error(f"USER IMPACT: Monero POS Payment Method experienced an Error with RPC: {e.__class__.__name__}")
                raise ValidationError("Current technical issues prevent Monero from being accepted, choose another payment method")

            res = {
                "wallet_address": wallet.new_address()[0],
            }
        else:
            _logger.error("USER IMPACT: Monero POS Payment Method experienced an Error with payment method: Not Found")
            raise ValidationError("Current technical issues prevent Monero from being accepted, choose another payment method")

        return res
