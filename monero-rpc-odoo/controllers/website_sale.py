import logging

from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.exceptions import ValidationError
from odoo.http import request

from ..models.exceptions import MoneroPaymentAcquirerRPCUnauthorized
from ..models.exceptions import MoneroPaymentAcquirerRPCSSLError

_logger = logging.getLogger(__name__)


class MoneroWebsiteSale(WebsiteSale):

    def _get_shop_payment_values(self, order, **kwargs):
        """
        Override to generate a Monero subaddress when the Monero RPC provider
        is available, so it can be passed to the payment form.
        """
        render_values = super()._get_shop_payment_values(order, **kwargs)

        for provider in render_values.get("payment_providers", []):
            if provider.code == "monero_rpc":
                try:
                    wallet = provider.get_wallet()
                    request.wallet_address = wallet.new_address()[0]
                    _logger.debug("new monero payment subaddress generated")
                except MoneroPaymentAcquirerRPCUnauthorized:
                    _logger.error(
                        "USER IMPACT: Monero Payment Provider "
                        "can't authenticate with RPC "
                        "due to user name or password"
                    )
                    raise ValidationError(
                        "Current technical issues prevent Monero from being accepted, "
                        "choose another payment method"
                    )
                except MoneroPaymentAcquirerRPCSSLError:
                    _logger.error(
                        "USER IMPACT: Monero Payment Provider "
                        "experienced an SSL Error with RPC"
                    )
                    raise ValidationError(
                        "Current technical issues prevent Monero from being accepted, "
                        "choose another payment method"
                    )
                except Exception as e:
                    _logger.error(
                        f"USER IMPACT: Monero Payment Provider "
                        f"experienced an Error with RPC: {e.__class__.__name__}"
                    )
                    raise ValidationError(
                        "Current technical issues prevent Monero from being accepted, "
                        "choose another payment method"
                    )

        return render_values
