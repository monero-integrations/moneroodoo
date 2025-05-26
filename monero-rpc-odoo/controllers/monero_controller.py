import logging

from odoo import http
# Cannot import, need to write it ourselfes...
# from odoo.addons.payment.controllers.portal import PaymentProcessing
from odoo.http import request

_logger = logging.getLogger(__name__)


class MoneroController(http.Controller):
    _accept_url = '/payment/monero/feedback'

    @http.route(
        "/shop/payment/token", type="http", auth="public", website=True, sitemap=False
    )
    def payment_token(self, pm_id: int | None = None, **kwargs):
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
            pm_id = int(pm_id) # type: ignore
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
            add_payment_transaction(transaction)
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
                add_payment_transaction(transaction)
                return request.redirect("/shop/payment/validate")

            add_payment_transaction(transaction)
            return request.redirect("/payment/process")

    @http.route(_accept_url, type='http', auth='public', methods=['POST'], csrf=False)
    def transfer_form_feedback(self, sale_id=None, **post):
        # calls monero_transaction _get_tx_from_feedback_data
        if sale_id:
            request.session["sale_last_order_id"] = sale_id
        request.env['payment.transaction'].sudo()._handle_feedback_data('monero-rpc', post)
        return request.redirect("/payment/status")


def remove_payment_transaction(transactions):
    tx_ids_list = request.session.get("__payment_tx_ids__", [])
    if transactions:
        for tx in transactions:
            if tx.id in tx_ids_list:
                tx_ids_list.remove(tx.id)
    else:
        return False
    request.session["__payment_tx_ids__"] = tx_ids_list
    return True


def add_payment_transaction(transactions):
    if not transactions:
        return False
    tx_ids_list = set(request.session.get("__payment_tx_ids__", [])) | set(transactions.ids)
    request.session["__payment_tx_ids__"] = list(tx_ids_list)
    return True
