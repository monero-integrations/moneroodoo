# -*- coding: utf-8 -*-
import logging
from odoo import fields, models

_logger = logging.getLogger(__name__)


class MoneroSalesOrder(models.Model):
    _inherit = "sale.order"

    def _get_transaction_id(self):
        for record in self:
            payment = self.env["payment.transaction"].search(
                [("sale_order_id", "=", record.id)], limit=1
            )
            if payment:
                record.transaction = payment.id
            else:
                record.transaction = False

    is_payment_recorded = fields.Boolean(
        "Is the Payment Recorded in this ERP",
        help="Cryptocurrency transactions need to be recorded and "
             "associated with this server for order handling.",
        default=False,
    )
    transaction = fields.Many2one(
        "payment.transaction",
        string="Transaction",
        compute=_get_transaction_id
    )

    # An order that is submitted,
    # will have a sale order,
    # an associated invoice,
    # a payment, and a payment token
    # check if the payment has been completed, if so mark the payment as done
    def salesorder_payment_sync(self):
        # retrieve all the cryptocurrency payment acquirers
        # TODO search 'is_enabled' '=' True?
        cryptocurrency_payment_acquirers = self.env["payment.acquirer"].search(
            [("is_cryptocurrency", "=", True)]
        )

        for acquirer in cryptocurrency_payment_acquirers:
            pass
            # TODO
