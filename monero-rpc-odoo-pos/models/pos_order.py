import logging

from odoo import models

_logger = logging.getLogger(__name__)


class MoneroPosOrder(models.Model):
    _inherit = "pos.order"
