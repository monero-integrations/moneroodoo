from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging
import requests
import json

_logger = logging.getLogger(__name__)

class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    payment_provider_id = fields.Many2one(
        'payment.provider',
        string='Payment Provider',
        domain="[('code', '=', 'monero_rpc')]",
        help="Linked Monero payment provider configuration",
    )

    is_monero = fields.Boolean(
        string='Is Monero Payment',
        compute='_compute_is_monero',
        readonly=True,
        store=True
    )
    qr_size = fields.Integer(
        string='QR Code Size', 
        default=200,
        help="Size of generated QR codes in pixels"
    )
    payment_timeout = fields.Integer(
        string='Payment Timeout (minutes)',
        default=180,
        help="Time before payment request expires"
    )

    @api.depends('payment_provider_id')
    def _compute_is_monero(self):
        for method in self:
            method.is_monero = method.payment_provider_id.code == 'monero_rpc'
            if method.is_monero:
                _logger.debug("This is a Monero Payment Provider")
            else: 
                _logger.debug("This is NOT a Monero Payment Provider")            


    def _get_payment_terminal_selection(self):
        selection = super()._get_payment_terminal_selection()
        selection.append(('monero_rpc', 'Monero RPC'))
        return selection

    def _convert_to_xmr(self, amount, currency):
        """Convert amount to XMR using provider's exchange rate"""
        self.ensure_one()
        if not self.payment_provider_id:
            raise ValidationError(_("No Monero payment provider configured"))
        
        try:
            rate = self.payment_provider_id._get_monero_exchange_rate(currency)
            return amount / rate
        except Exception as e:
            raise ValidationError(
                _("XMR conversion failed: %s") % str(e)
            )

    @api.constrains('payment_provider_id', 'use_payment_terminal')
    def _check_monero_config(self):
        for method in self:
            if method.use_payment_terminal == 'monero_rpc' and not method.payment_provider_id:
                raise ValidationError(_("Monero payment method requires a linked payment provider"))


class PosOrder(models.Model):
    _inherit = 'pos.order'

    monero_payment_id = fields.Many2one('monero.payment', string='Monero Payment')
    monero_payment_status = fields.Selection(related='monero_payment_id.state', string='Payment Status')
    monero_confirmations = fields.Integer(related='monero_payment_id.confirmations', string='Confirmations')

    def _create_monero_payment(self, amount):
        self.ensure_one()
        Payment = self.env['monero.payment']
        return Payment.create({
            'amount': amount,
            'currency': self.currency_id.name,
            'order_ref': self.pos_reference,
            'description': f"POS Order {self.pos_reference}"
        })

    def _process_monero_payment(self, payment_method, amount):
        self.ensure_one()
        monero_payment = self._create_monero_payment(amount)
        self.write({'monero_payment_id': monero_payment.id})
        
        return {
            'payment_id': monero_payment.id,
            'address': payment_method.monero_wallet_address,
            'amount': amount,
            'currency': self.currency_id.name,
            'qr_code_url': f"/monero/qr/{monero_payment.id}?size={payment_method.monero_qr_size}"
        }
