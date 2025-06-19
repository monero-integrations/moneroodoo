from odoo import models, fields, api


class MoneroTransaction(models.Model):
    _name = 'monero.transaction'
    _description = 'Monero Transaction'
    _order = 'timestamp desc'

    payment_id = fields.Many2one(
        'monero.payment',
        string="Payment",
        required=True,
        ondelete='cascade')
    txid = fields.Char(string="Transaction Hash", required=True, index=True)
    amount = fields.Float(string="Amount", digits=(12, 12), required=True)
    fee = fields.Float(string="Fee", digits=(12, 12))
    block_height = fields.Integer(string="Block Height", index=True)
    unlock_time = fields.Integer(string="Unlock Time")
    confirmations = fields.Integer(string="Confirmations", compute='_compute_confirmations', store=True)
    timestamp = fields.Datetime(string="Timestamp", required=True)
    is_confirmed = fields.Boolean(string="Confirmed", compute='_compute_is_confirmed', store=True)
    payment_type = fields.Selection([
        ('in', 'Incoming'),
        ('out', 'Outgoing'),
        ('pending', 'Pending'),
        ('failed', 'Failed')],
        string="Type")

    @api.depends('block_height')
    def _compute_confirmations(self):
        for tx in self:
            if not tx.block_height:
                tx.confirmations = 0
                continue
                
            current_height = self.env['monero.payment']._get_current_block_height()
            tx.confirmations = max(0, current_height - tx.block_height) if current_height else 0

    @api.depends('confirmations')
    def _compute_is_confirmed(self):
        threshold = self.env['payment.provider']._get_monero_provider().confirmation_threshold
        for tx in self:
            tx.is_confirmed = tx.confirmations >= threshold
