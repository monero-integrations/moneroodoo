import logging

from odoo import http
from odoo.http import request
from monero.address import SubAddress

_logger = logging.getLogger(__name__)

class MoneroController(http.Controller):

    @http.route("/shop/payment/monero/submit", type="json", auth="public", website=True)
    def monero_transaction(self, verify_validity=False, **kwargs):
        """Handles Monero transactions by creating payment tokens and transactions."""

        sales_order = request.website.sale_get_order()
        if not sales_order or not sales_order.order_line:
            return False

        _logger.info(f"Processing sales_order: {sales_order.id}")

        # Ensure Monero is the selected currency
        currency = request.env["res.currency"].sudo().browse(sales_order.currency_id.id)
        if currency.name != "XMR":
            raise Exception("Please select the Monero Pricelist before checkout.")

        # Extract payment details
        payment_provider_id = int(kwargs.get("provider_id"))
        payment_partner_id = int(kwargs.get("partner_id"))
        wallet_sub_address = SubAddress(kwargs.get("wallet_address"))

        # Prevent duplicate usage of Monero subaddresses
        existing_tokens = request.env["payment.token"].sudo().search([
            ("name", "=", wallet_sub_address)
        ])
        if existing_tokens:
            raise Exception("This Monero subaddress has already been used.")

        # Create payment token (inactive to prevent reuse)
        payment_token = request.env["payment.token"].sudo().create({
            "name": str(wallet_sub_address),
            "partner_id": payment_partner_id,
            "active": False,
            "provider_id": payment_provider_id,
            "provider_ref": "payment.payment_provider_monero_rpc",
        })

        _logger.info(f"Created payment token {payment_token.id} for sales_order: {sales_order.id}")

        # Prepare transaction values
        tx_values = {
            "amount": sales_order.amount_total,
            "reference": sales_order.name,
            "currency_id": sales_order.currency_id.id,
            "partner_id": sales_order.partner_id.id,
            "payment_token_id": payment_token.id,
            "provider_id": payment_provider_id,
            "state": "pending",
        }

        # Check for an existing transaction
        transaction = sales_order.get_portal_last_transaction()
        if not transaction:
            transaction = request.env["payment.transaction"].sudo().create(tx_values)
            _logger.info(f"Created transaction: {transaction.id}")
        else:
            _logger.info(f"Using existing transaction: {transaction.id}")

        # Remove old transaction from session (if exists) and store the new one
        last_tx_id = request.session.get("__website_sale_last_tx_id")
        if last_tx_id:
            last_tx = request.env["payment.transaction"].sudo().browse(last_tx_id).exists()
            if last_tx:
                last_tx.sudo().unlink()

        request.session["__website_sale_last_tx_id"] = transaction.id

        # Mark sales order as "sent" (awaiting payment confirmation)
        sales_order.sudo().write({"require_payment": "true", "state": "sent"})

        # Determine queue settings based on required confirmations
        payment_provider = request.env["payment.provider"].sudo().browse(payment_provider_id)
        num_conf_req = int(payment_provider.num_confirmation_required)

        queue_channel = "monero_secure_processing" if num_conf_req else "monero_zeroconf_processing"
        queue_max_retries = max(44, num_conf_req * 25)

        # Queue the transaction for processing
        sales_order.with_delay(channel=queue_channel, max_retries=queue_max_retries).process_transaction(
            transaction, payment_token, num_conf_req
        )

        # Return transaction details
        response = {
            "result": True,
            "id": payment_token.id,
            "short_name": payment_token.short_name,
            "3d_secure": False,
            "verified": False,
        }

        if verify_validity:
            payment_token.validate()
            response["verified"] = payment_token.verified

        return response

    @http.route("/shop/payment/token", type="http", auth="public", website=True, sitemap=False)
    def payment_token(self, pm_id=None, **kwargs):
        """Handles payments using saved Monero payment tokens."""

        sales_order = request.website.sale_get_order()
        if not sales_order:
            return request.redirect("/shop/?error=no_order")

        try:
            pm_id = int(pm_id)
        except ValueError:
            return request.redirect("/shop/?error=invalid_token_id")

        payment_token = request.env["payment.token"].sudo().browse(pm_id)
        if not payment_token:
            return request.redirect("/shop/?error=token_not_found")

        last_tx_id = request.session.get("__website_sale_last_tx_id")
        if last_tx_id:
            transaction = request.env["payment.transaction"].sudo().browse(last_tx_id)
            request.session["__website_sale_last_tx_id"] = None
            return request.redirect("/shop/payment/validate")

        # Create a new payment transaction
        tx_values = {
            "payment_token_id": pm_id,
            "return_url": "/shop/payment/validate",
        }
        transaction = request.env["payment.transaction"].sudo().create(tx_values)
        _logger.info(f"Created transaction: {transaction.id} for token: {payment_token.id}")

        if transaction.provider_id.is_cryptocurrency:
            sales_order.sudo().write({"state": "sent"})
            transaction.sudo().write({"state": "pending"})
            return request.redirect("/shop/payment/validate")

        return request.redirect("/payment/process")
