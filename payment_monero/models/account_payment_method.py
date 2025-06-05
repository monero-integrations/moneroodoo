# -*- coding: utf-8 -*-

from typing_extensions import override

from odoo import api
from odoo.addons.account.models import account_payment_method

class MoneroAccountPaymentMethod(account_payment_method.AccountPaymentMethod):
    _inherit = 'account.payment.method'

    @api.model
    @override
    def _get_payment_method_information(self):
        res = super()._get_payment_method_information()
        res['monero'] = {'mode': 'unique', 'domain': [('type', '=', 'bank')]}
        return res
