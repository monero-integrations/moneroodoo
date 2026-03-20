import logging

from odoo import http
from odoo.addons.payment.controllers.post_processing import PaymentPostProcessing
from odoo.http import request
from monero.address import SubAddress

_logger = logging.getLogger(__name__)


class MoneroController(http.Controller):
    @http.route("/shop/payment/monero/submit", type="json", auth="public", website=True)
    def monero_transaction(self, verify_validity=False, **kwargs):
        """
        Function creates a transaction and payment token using the sessions sales order.
        :param verify_validity:
        :param kwargs:
        :return:
        """
        # In Odoo 19, request.cart replaces request.website.sale_get_order()
        sales_order = request.cart
        if not sales_order:
            _logger.error("no cart/order found")
            return False

        _logger.info(f"received sales_order: {sales_order.id}")
        _logger.info(f"processing sales_order: {sales_order.id}")

        # Ensure there is something to proceed
        if not sales_order.order_line:
            return False

        assert sales_order.partner_id.id != request.website.partner_id.id

        # at this time the sales order has to be in xmr
        currency = request.env["res.currency"].sudo().browse(sales_order.currency_id.id)
        if currency.name != "XMR":
            raise Exception(
                "This pricelist is not supported, go back and select the "
                "Monero Pricelist"
            )

        payment_provider_id = int(kwargs.get("acquirer_id"))
        payment_partner_id = int(kwargs.get("partner_id"))
        wallet_sub_address = SubAddress(kwargs.get("wallet_address"))

        # security check, enforce one time usage of subaddresses
        payment_tokens = (
            request.env["payment.token"]
            .sudo()
            .search([("provider_ref", "=", str(wallet_sub_address))])
        )
        assert len(payment_tokens) < 1

        # Get the monero payment method
        payment_method = (
            request.env["payment.method"]
            .sudo()
            .search([("code", "=", "monero_rpc")], limit=1)
        )

        # define payment token
        payment_token_vals = {
            "provider_ref": str(wallet_sub_address),
            "payment_details": str(wallet_sub_address)[:20] + "...",
            "partner_id": payment_partner_id,
            "active": False,
            # token shouldn't be active, the subaddress shouldn't be reused
            "provider_id": payment_provider_id,
            "payment_method_id": payment_method.id,
        }

        _logger.info(f"creating payment token for sales_order: {sales_order.id}")
        token = request.env["payment.token"].sudo().create(payment_token_vals)
        token_id = token.id

        # assign values for transaction creation
        tx_val = {
            "amount": sales_order.amount_total,
            "reference": sales_order.name,
            "currency_id": sales_order.currency_id.id,
            "partner_id": sales_order.partner_id.id,
            "token_id": token_id,
            "provider_id": payment_provider_id,
            "payment_method_id": payment_method.id,
            "state": "pending",
        }

        _logger.info(f"getting the transaction for sales_order: {sales_order.id}")
        transaction = sales_order.get_portal_last_transaction()
        if transaction.id is False:
            transaction = sales_order._create_payment_transaction(tx_val)
            _logger.info(f"created transaction: {transaction.id}")
        else:
            _logger.info(f"retrieved transaction: {transaction.id}")

        # store the new transaction into the session
        last_tx_id = request.session.get("__website_sale_last_tx_id")
        last_tx = request.env["payment.transaction"].browse(last_tx_id).sudo().exists()
        if last_tx:
            PaymentPostProcessing.monitor_transaction(transaction)
            request.session["__website_sale_last_tx_id"] = transaction.id

        # Sale Order is quotation sent
        _logger.info(
            f'setting sales_order state to "sent" for sales_order: {sales_order.id}'
        )
        request.env.user.sale_order_ids.sudo().update(
            {"require_payment": "true", "state": "sent"}
        )

        payment_provider = (
            request.env["payment.provider"].sudo().browse(payment_provider_id)
        )
        # set queue channel and interval settings depending on num conf settings
        num_conf_req = int(payment_provider.num_confirmation_required)
        if num_conf_req == 0:
            queue_channel = "monero_zeroconf_processing"
        else:
            queue_channel = "monero_secure_processing"

        # Create server action for the transaction processing
        action = request.env['ir.actions.server'].create({
            'name': f'Monero Transaction Processing ({queue_channel})',
            'model_id': request.env['ir.model']._get_id('sale.order'),
            'state': 'code',
            'code': f"""
record = env['sale.order'].browse({sales_order.id})
record.process_transaction(
    env['payment.transaction'].browse({transaction.id}),
    env['payment.token'].browse({token.id}),
    {num_conf_req}
)
""",
        })

        # Create cron job with appropriate interval based on channel
        if queue_channel == "monero_zeroconf_processing":
            interval_number = 15  # Check every 15 minutes for zero-conf
        else:
            interval_number = 60  # Check every hour for secure processing

        cron = request.env['ir.cron'].create({
            'name': f'Monero Processing ({queue_channel}) - {sales_order.name}',
            'ir_actions_server_id': action.id,
            'user_id': request.env.user.id,
            'active': True,
            'interval_number': interval_number,
            'interval_type': 'minutes',
        })

        # Trigger immediately for first check
        cron._trigger()

        if transaction:
            redirect_form_html = (
                f'<form action="/shop/payment/token" method="GET">'
                f'<input type="hidden" name="pm_id" value="{token_id}" />'
                "</form>"
            )
            return {"redirect_form_html": redirect_form_html}

    @http.route(
        "/shop/payment/token", type="http", auth="public", website=True, sitemap=False
    )
    def payment_token(self, pm_id=None, **kwargs):
        """OVERRIDING METHOD FROM odoo/addons/website_sale/controllers/main.py
        Method that handles payment using saved tokens.
        :param int pm_id: id of the payment.token that we want to use to pay.
        """
        # In Odoo 19, request.cart replaces request.website.sale_get_order()
        sales_order = request.cart
        _logger.info(f"received token for sales_order: {sales_order.id if sales_order else 'None'}")

        # do not crash if the user has already paid and try to pay again
        if not sales_order:
            _logger.error("no order found")
            return request.redirect("/shop/?error=no_order")

        assert sales_order.partner_id.id != request.website.partner_id.id

        try:
            pm_id = int(pm_id)
        except (ValueError, TypeError):
            _logger.error("invalid token id")
            return request.redirect("/shop/?error=invalid_token_id")

        # payment token already created, get it
        token = request.env["payment.token"].sudo().browse(pm_id)

        if not token:
            return request.redirect("/shop/?error=token_not_found")

        # has the transaction already been created?
        tx_id = request.session.get("__website_sale_last_tx_id")
        if tx_id:
            transaction = request.env["payment.transaction"].sudo().browse(tx_id)
            PaymentPostProcessing.monitor_transaction(transaction)
            request.session["__website_sale_last_tx_id"] = None
            return request.redirect("/shop/payment/validate")
        else:
            # Get the monero payment method
            payment_method = (
                request.env["payment.method"]
                .sudo()
                .search([("code", "=", "monero_rpc")], limit=1)
            )
            tx_val = {
                "token_id": pm_id,
                "payment_method_id": payment_method.id,
                "landing_route": "/shop/payment/validate",
            }
            transaction = sales_order._create_payment_transaction(tx_val)
            _logger.info(
                f"created transaction: {transaction.id} "
                f"for payment token: {token.id}"
            )
            if transaction.provider_id.is_cryptocurrency:
                _logger.info(
                    f"Processing cryptocurrency "
                    f"payment provider: {transaction.provider_id.name}"
                )
                sales_order.sudo().update({"state": "sent"})
                transaction.sudo()._set_pending()
                PaymentPostProcessing.monitor_transaction(transaction)
                return request.redirect("/shop/payment/validate")

            PaymentPostProcessing.monitor_transaction(transaction)
            return request.redirect("/payment/status")
