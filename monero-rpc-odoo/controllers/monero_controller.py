import logging

from odoo import http

_logger = logging.getLogger(__name__)

# The Monero payment flow in Odoo 19 uses the standard payment provider redirect flow:
#
#   Buyer clicks Pay
#     → /shop/payment/transaction/<order_id>  (standard Odoo route)
#     → creates payment.transaction (operation='online_redirect')
#     → calls MoneroPaymentTransaction._get_specific_rendering_values()
#         → generates Monero subaddress via RPC
#         → creates payment.token with subaddress
#         → sets up ir.cron for payment polling
#         → returns rendering values for monero_redirect_form template
#     → renders monero_redirect_form.xml → redirect_form_html returned to JS
#   JS submits the form → redirects to /payment/status
#   Cron polls wallet RPC → confirms payment → order confirmed
#
# No custom controller routes are needed for the payment initiation.
# The cron job calls sale.order.process_transaction() to poll and confirm.
