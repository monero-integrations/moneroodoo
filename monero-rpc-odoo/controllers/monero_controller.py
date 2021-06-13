import logging

from odoo import http
from odoo.addons.payment.controllers.portal import PaymentProcessing
from odoo.http import request
from monero.address import SubAddress

_logger = logging.getLogger(__name__)


class MoneroController(http.Controller):
    @http.route("/shop/payment/monero/submit", type="json", auth="public", website=True)
    def monero_transaction(self, verify_validity=False, **kwargs):
        """
        Function creates a transaction and
        payment token using the sessions sales order
        Calls MoneroSalesOrder.salesorder_payment_sync()
        :param verify_validity:
        :param kwargs:
        :return:
        """
        sales_order = request.website.sale_get_order()
        _logger.info(f"received sales_order: {sales_order.id}")
        _logger.info(f"processing sales_order: {sales_order.id}")

        # Ensure there is something to proceed
        if not sales_order or (sales_order and not sales_order.order_line):
            return False

        assert sales_order.partner_id.id != request.website.partner_id.id
        # at this time the sales order has to be in xmr
        # the user cannot use a fiat pricelist when checking out
        # this won't be fixed until after a job is added to automatically
        # update res.currency.rate
        currency = request.env["res.currency"].sudo().browse(sales_order.currency_id.id)
        if currency.name != "XMR":
            raise Exception(
                "This pricelist is not supported, go back and select the "
                "Monero Pricelist"
            )

        payment_acquirer_id = int(kwargs.get("acquirer_id"))

        payment_partner_id = int(kwargs.get("partner_id"))

        wallet_sub_address = SubAddress(kwargs.get("wallet_address"))

        # security check, enforce one time usage of subaddresses
        payment_tokens = (
            request.env["payment.token"]
            .sudo()
            .search([("name", "=", wallet_sub_address)])
        )
        assert len(payment_tokens) < 1

        # define payment token
        payment_token = {
            "name": wallet_sub_address.__repr__(),
            "partner_id": payment_partner_id,
            # partner_id creating sales order
            "active": False,
            # token shoudn't be active, the subaddress shouldn't be reused
            "acquirer_id": payment_acquirer_id,
            # surrogate key for payment acquirer
            "acquirer_ref": "payment.payment_acquirer_monero_rpc",
        }

        _logger.info(f"creating payment token " f"for sales_order: {sales_order.id}")
        token = request.env["payment.token"].sudo().create(payment_token)
        token_id = token.id
        token_short_name = token.short_name

        # assign values for transaction creation
        tx_val = {
            "amount": sales_order.amount_total,
            "reference": sales_order.name,
            "currency_id": sales_order.currency_id.id,
            "partner_id": sales_order.partner_id.id,
            # Referencing the Sale Order Partner ID
            "payment_token_id": token_id,  # Associating the Payment Token ID.
            "acquirer_id": payment_acquirer_id,  # Payment Acquirer - Monero
            "state": "pending",
            # tx is pending,
            # because the customer will know the address to send the tx to,
            # but hasn't yet sent it
        }

        _logger.info(f"getting the transaction " f"for sales_order: {sales_order.id}")
        # transaction = sales_order._create_payment_transaction(tx_val)
        transaction = sales_order.get_portal_last_transaction()
        if transaction.id is False:
            transaction = sales_order._create_payment_transaction(tx_val)
            _logger.info(f"created transaction: {transaction.id}")
        else:
            _logger.info(f"retrieved transaction: {transaction.id}")

        # store the new transaction into
        # the transaction list and if there's an old one, we remove it
        # until the day the ecommerce supports multiple orders at the same time
        last_tx_id = request.session.get("__website_sale_last_tx_id")
        last_tx = request.env["payment.transaction"].browse(last_tx_id).sudo().exists()
        if last_tx:
            PaymentProcessing.remove_payment_transaction(last_tx)
        PaymentProcessing.add_payment_transaction(transaction)
        request.session["__website_sale_last_tx_id"] = transaction.id

        # Sale Order is quotation sent
        #   , so the state should be set to "sent"
        #   , until the transaction has been verified
        _logger.info(
            f'setting sales_order state to "sent" ' f"for sales_order: {sales_order.id}"
        )
        request.env.user.sale_order_ids.sudo().update(
            {"require_payment": "true", "state": "sent"}
        )

        payment_acquirer = (
            request.env["payment.acquirer"].sudo().browse(payment_acquirer_id)
        )
        # set queue channel and max_retries settings
        # for queue depending on num conf settings
        num_conf_req = int(payment_acquirer.num_confirmation_required)
        if num_conf_req == 0:
            queue_channel = "monero_zeroconf_processing"
            queue_max_retries = 44
        else:
            queue_channel = "monero_secure_processing"
            queue_max_retries = num_conf_req * 25

        # Add payment token and sale order to transaction processing queue

        sales_order.with_delay(
            channel=queue_channel, max_retries=queue_max_retries
        ).process_transaction(transaction, token, num_conf_req)

        if transaction:
            res = {
                "result": True,
                "id": token_id,
                "short_name": token_short_name,
                "3d_secure": False,
                "verified": False,
            }

            if verify_validity is not False:
                token.validate()
                res["verified"] = token.verified

            return res

    @http.route(
        "/shop/payment/token", type="http", auth="public", website=True, sitemap=False
    )
    def payment_token(self, pm_id=None, **kwargs):
        """OVERRIDING METHOD FROM odoo/addons/website_sale/controllers/main.py
        Method that handles payment using saved tokens
        :param int pm_id: id of the payment.token that we want to use to pay.

        This route is requested after payment submission :
            /shop/payment/monero/submit - it's called everytime,
            since we will use monero sub addresses
            as one time addresses
        """

        # order already created, get it
        sales_order = request.website.sale_get_order()
        _logger.info(f"received token for sales_order: {sales_order.id}")
        _logger.info(f"processing token for sales_order: {sales_order.id}")

        # do not crash if the user has already paid and try to pay again
        if not sales_order:
            _logger.error("no order found")
            return request.redirect("/shop/?error=no_order")

        # see overriden method
        assert sales_order.partner_id.id != request.website.partner_id.id

        try:
            # pm_id is passed, make sure it's a valid int
            pm_id = int(pm_id)
        except ValueError:
            _logger.error("invalid token id")
            return request.redirect("/shop/?error=invalid_token_id")

        # payment token already created, get it
        token = request.env["payment.token"].sudo().browse(pm_id)

        if not token:
            return request.redirect("/shop/?error=token_not_found")

        # has the transaction already been created?
        tx_id = request.session["__website_sale_last_tx_id"]
        if tx_id:
            # transaction was already
            # established in /shop/payment/monero/submit
            transaction = request.env["payment.transaction"].sudo().browse(tx_id)
            PaymentProcessing.add_payment_transaction(transaction)
            # clear the tx in session, because we're done with it
            request.session["__website_sale_last_tx_id"] = None
            return request.redirect("/shop/payment/validate")
        else:
            # transaction hasn't been created
            tx_val = {"payment_token_id": pm_id, "return_url": "/shop/payment/validate"}
            transaction = sales_order._create_payment_transaction(tx_val)
            _logger.info(
                f"created transaction: {transaction.id} "
                f"for payment token: {token.id}"
            )
            if transaction.acquirer_id.is_cryptocurrency:
                _logger.info(
                    f"Processing cryptocurrency "
                    f"payment acquirer: {transaction.acquirer_id.name}"
                )
                _logger.info(
                    f"setting sales_order state to "
                    f'"sent" for sales_order: {sales_order.id}'
                )
                sales_order.sudo().update({"state": "sent"})
                _logger.info(
                    f"setting transaction state to "
                    f'"pending" for sales_order: {sales_order.id}'
                )
                transaction.sudo().update({"state": "pending"})
                PaymentProcessing.add_payment_transaction(transaction)
                return request.redirect("/shop/payment/validate")

            PaymentProcessing.add_payment_transaction(transaction)
            return request.redirect("/payment/process")
