import logging
import secrets
import base64
import hashlib
import json
from decimal import Decimal
from io import BytesIO
from datetime import datetime, timedelta

import qrcode
import monero
import urllib.parse
from monero.wallet import Wallet
from monero.backends.jsonrpc import JSONRPCWallet
from monero.daemon import Daemon

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)


class MoneroPayment(models.Model):
    _name = 'monero.payment'
    _description = 'Monero Payment'
    _order = 'create_date desc'
    _rec_name = 'display_name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    display_name = fields.Char(
        string="Reference",
        compute='_compute_display_name',
        store=True)
    payment_id = fields.Integer(
        string="Payment ID",
        required=True,
        readonly=True,
        index=True)
    sale_order_id = fields.Many2one(
        'sale.order',
        string="Sales Order",
        readonly=True,
        index=True)    
    address_seller = fields.Char(
        string="Receiving Address",
        readonly=True,
        required=True)
    address_buyer = fields.Char(string="Buyer Address")
    subaddress_index = fields.Integer(
        string="Subaddress Index",
        readonly=True)
    amount = fields.Float(
        string="Amount (XMR)",
        required=True,
        digits=(12, 12))
    amount_received = fields.Float(
        string="Amount Received (XMR)",
        readonly=True,
        digits=(12, 12),
        default=0.0)
    amount_due = fields.Float(
        string="Amount Due (XMR)",
        compute='_compute_amount_due',
        digits=(12, 12))
    currency = fields.Char(
        string="Currency",
        default="XMR",
        required=True,
        readonly=True)
    order_ref = fields.Char(
        string="Order Reference",
        index=True)
    description = fields.Text(string="Description")
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('pending', 'Pending Payment'),
            ('partial', 'Partially Paid'),
            ('paid_unconfirmed', 'Paid (Unconfirmed)'),
            ('confirmed', 'Confirmed'),
            ('expired', 'Expired'),
            ('failed', 'Failed'),
            ('overpaid', 'Overpaid')],
        string='Status',
        default='draft',
        readonly=True,
        index=True,
        tracking=True)
    confirmations = fields.Integer(
        string="Confirmations",
        readonly=True,
        compute='_compute_confirmations',
        store=True)
    expiration = fields.Datetime(
        string="Expiration Date",
        required=True,
        default=lambda self: fields.Datetime.now() + timedelta(hours=1))
    create_date = fields.Datetime(
        string="Creation Date",
        readonly=True)
    error_message = fields.Text(
        string="Error Message",
        readonly=True)
    transaction_ids = fields.One2many(
        'monero.transaction',
        'payment_id',
        string="Transactions")
    original_amount = fields.Float(
        string="Original Amount",
        digits=(16, 2))
    original_currency = fields.Char(
        string="Original Currency",
        default="USD")
    exchange_rate = fields.Float(
        string="Exchange Rate",
        digits=(16, 6))
    image_qr = fields.Char(
        string="QR Code",
        compute='_compute_qr_code')
    last_check = fields.Datetime(
        string="Last checked")
    qr_code_uri = fields.Char(
        string="Monero URI",
        compute='_compute_qr_code_uri')
    is_subaddress = fields.Boolean(
        string="Uses Subaddress",
        default=True,
        readonly=True)

    _sql_constraints = [
        ('payment_id_unique', 'UNIQUE(payment_id)', 'Payment ID must be unique!'),
        ('amount_positive', 'CHECK(amount > 0)', 'Amount must be positive!'),
    ]

    @api.depends('order_ref', 'amount', 'currency')
    def _compute_display_name(self):
        for payment in self:
            payment.display_name = f"{payment.order_ref or 'Payment'} - {payment.amount:.12f} {payment.currency}"

    @api.depends('amount', 'amount_received')
    def _compute_amount_due(self):
        for payment in self:
            payment.amount_due = max(0.0, payment.amount - payment.amount_received)

    @api.depends('transaction_ids.confirmations')
    def _compute_confirmations(self):
        for payment in self:
            if not payment.transaction_ids:
                payment.confirmations = 0
            else:
                payment.confirmations = min(
                    tx.confirmations for tx in payment.transaction_ids 
                    if tx.confirmations is not None)

    @api.depends('address_seller', 'amount', 'payment_id', 'order_ref')
    def _compute_qr_code_uri(self):
        for payment in self:
            if payment.address_seller:
                desc = f"Order {payment.order_ref}" if payment.order_ref else "Payment"
                payment.qr_code_uri = (
                    f"monero:{payment.address_seller}"
                    f"?tx_amount={payment.amount:.12f}"
                    f"&tx_payment_id={payment.payment_id}"
                    f"&tx_description={desc}"
                )
            else:
                payment.qr_code_uri = False

    @api.depends('qr_code_uri')
    def _compute_qr_code(self):
        for payment in self:
            if payment.qr_code_uri:
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=4,
                )
                qr.add_data(payment.qr_code_uri)
                qr.make(fit=True)
                
                img = qr.make_image()
                buffered = BytesIO()
                img.save(buffered, format="PNG")
                payment.image_qr = base64.b64encode(buffered.getvalue())
            else:
                payment.image_qr = False

    @api.model_create_multi
    def create(self, vals):
        _logger.debug("Creating...%s", vals)
        
        vals = vals[0]
        if not vals['payment_id']:
            vals['payment_id'] = secrets.token_hex(32)
                
        return super().create(vals)

    @api.model
    def _get_current_block_height(self):
        """Get current blockchain height"""
        provider = self.env['payment.provider']._get_monero_provider()
        try:
            daemon = provider._get_daemon()
            return daemon.height()
        except Exception as e:
            _logger.error("Failed to get block height: %s", str(e))
            return 0

    def refresh_exchange_rate(self):
        """Refresh the exchange rate for this payment"""
        self.ensure_one()
        provider = self.env['payment.provider']._get_monero_provider()
        try:
            rate = provider._get_xmr_exchange_rate(self.original_currency)
            if rate:
                self.exchange_rate = rate
                return True
        except Exception as e:
            _logger.error("Failed to fetch exchange rate: %s", str(e))
        return False
        
    def serialize_transfer(self, transfer):
        data = {}
        for key, value in transfer.__dict__.items():
            if isinstance(value, Decimal):
                data[key] = float(str(value))
            elif isinstance(value, datetime):
                data[key] = value.isoformat()
            elif hasattr(value, '__str__'):
                data[key] = str(value)
            else:
                data[key] = value
        return data

    def check_payment_status(self, paymentId):
        """Check payment status for specific subaddress minor index"""
        self.ensure_one()
        provider = self.env['payment.provider']._get_monero_provider()
        moneroPayment = self.env['monero.payment'].search([('payment_id', '=', int(paymentId))], limit=1)
        
        try:
            wallet = provider._get_wallet_client()
            current_height = moneroPayment._get_current_block_height()
            
            all_incoming = wallet.incoming()
            filtered = [
                t for t in all_incoming 
                if getattr(t, "local_address", None) == moneroPayment.address_seller
            ]
            _logger.debug("All incoming transfers: %s", filtered)

            _logger.info("Found %d payment(s) for subaddress index=%d", len(filtered), int(paymentId))

            transactions = []
            total_received = Decimal('0.0')
            
            for transfer in filtered:
                tx_data = {
                    'txid': transfer.transaction.hash,
                    'amount': float(transfer.amount),
                    'fee': float(transfer.transaction.fee),
                    'block_height': transfer.transaction.height,
                    'timestamp': transfer.transaction.timestamp,
                    'confirmations': transfer.transaction.confirmations,
                    'payment_id': moneroPayment.id,
                }
                transactions.append(tx_data)
                total_received += Decimal(str(transfer.amount))
            
            amount_received_float = float(total_received)
            amount_expected_float = float(Decimal(str(self.amount)))
            
            amount_compare = float_compare(
                amount_received_float,
                amount_expected_float,
                precision_digits=12
            )
            
            new_state = 'pending'
            if amount_compare == 0:
                for t in filtered:
                    _logger.debug("Confirmation - monero_payment - %d, %d", t.transaction.confirmations, provider.confirmation_threshold)
                    if t.transaction.confirmations >= provider.confirmation_threshold:
                        new_state = 'confirmed'
                        self._payment_confirmed(moneroPayment, {
                            'amount_received': total_received,
                            'state': new_state,
                            'last_check': fields.Datetime.now(),
                            'confirmations': max((t['confirmations'] for t in transactions), default=0)
                        })
                        break
                    else:
                        _logger.debug("Payment made but unconfirmed")
                        new_state = 'paid_unconfirmed'
            elif amount_compare == -1:
                new_state = 'partial' if total_received > 0 else 'pending'
            else:
                new_state = 'overpaid'
            
            self.transaction_ids.unlink()
            if transactions:
                self.env['monero.transaction'].create(transactions)
            
            update_vals = {
                'amount_received': total_received,
                'state': new_state,
                'last_check': fields.Datetime.now(),
                'confirmations': max((t['confirmations'] for t in transactions), default=0)
            }

            self.write(update_vals)
            
            return {
                'state': new_state,
                'amount_received': total_received,
                'confirmations': update_vals['confirmations'],
                'transactions': transactions
            }
        
        except Exception as e:
            _logger.error("Payment check failed: %s", str(e), exc_info=True)
            self._handle_rpc_error(str(e))
            return {
                'state': 'error',
                'error': str(e)
            }

            
    def generate_payment_proof(self):
        """Generate cryptographic proof of payment"""
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_("Payment must be confirmed to generate proof"))
            
        proof_data = {
            'payment_id': self.payment_id,
            'address': self.address,
            'amount': self.amount_received,
            'confirmations': self.confirmations,
            'tx_hashes': [tx.txid for tx in self.transaction_ids],
            'timestamp': fields.Datetime.now().isoformat(),
            'block_height': min(tx.block_height for tx in self.transaction_ids),
            'signature': self._generate_signature()
        }
        
        attachment = self.env['ir.attachment'].create({
            'name': f"Monero_Payment_Proof_{self.payment_id}.json",
            'type': 'binary',
            'datas': base64.b64encode(json.dumps(proof_data, indent=2).encode()),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/json'
        })
        
        return {
            'proof': proof_data,
            'attachment_id': attachment.id
        }

    def _generate_signature(self):
        """Create cryptographic signature for payment proof"""
        private_key = self.env['ir.config_parameter'].sudo().get_param(
            'monero.payment_proof_key')
        if not private_key:
            raise UserError(_("Payment proof system not configured - missing private key"))
        
        data = f"{self.payment_id}:{self.amount_received}:{self.address}"
        return hashlib.sha256((data + private_key).encode()).hexdigest()

    def _payment_confirmed(self, payment, values):
        """Handle confirmed payment"""
        try:
            self.write(values)

            if payment.sale_order_id:
                tx = self.env['payment.transaction'].sudo().search([
                    ('payment_id', '=', payment.id)
                ], limit=1)
                if tx:
                    tx._set_done()
                    if tx.state == 'done':
                        payment.sale_order_id._send_order_confirmation_mail() 
                                   
                order = self.env['sale.order'].search([
                    ('id', '=', self.sale_order_id.id)
                ], limit=1)
                if order:
                    try:
                        if order.state in ['draft', 'sent']:
                            order.with_context(send_email=True).action_confirm()
                        elif order.state == 'sale':
                            _logger.info(f"Order {self.order_ref} is already confirmed")
                        else:
                            _logger.warning(f"Order {self.order_ref} is in unexpected state {order.state}")
                    except Exception as e:
                        _logger.error(f"Failed to process order {self.order_ref}: {str(e)}")
            
            template = self.env.ref('payment_monero_rpc.email_template_payment_confirmed')
            template.send_mail(self.id, force_send=True)
            
            self.message_post(body=_(
                "Payment confirmed with %d confirmations. "
                "Amount received: %f XMR") % (
                self.confirmations,
                self.amount_received
            ))
        except Exception as e:
            _logger.error("Payment confirmation failed: %s", str(e))
            raise

    def _handle_rpc_error(self, error_message):
        """Handle RPC errors"""
        self.write({
            'error_message': error_message,
            'state': 'failed',
            'last_check': fields.Datetime.now()
        })

    @api.model
    def _cron_check_expired_payments(self):
        """Mark expired payments"""
        expired = self.search([
            ('state', 'in', ['pending', 'partial']),
            ('expiration', '<', fields.Datetime.now())
        ])
        expired.write({'state': 'expired'})
        _logger.info("Marked %d payments as expired", len(expired))

    @api.model
    def _cron_update_payment_rates(self):
        """Update exchange rates for pending payments"""
        pending_payments = self.search([
            ('state', 'in', ['pending', 'partial']),
            ('original_currency', '!=', 'XMR')
        ])
        
        for payment in pending_payments:
            try:
                payment.refresh_exchange_rate()
            except Exception as e:
                _logger.error("Failed to update rate for payment %d: %s", payment.id, str(e))

    @api.model
    def _cron_verify_pending_payments(self):
        """Scheduled job to verify pending payments"""
        payments = self.search([
            ('state', 'in', ['pending', 'partial', 'paid_unconfirmed']),
            ('expiration', '>', fields.Datetime.now())
        ], limit=100)  # Process in batches
        
        _logger.info("Checking %d pending payments...", len(payments))
        for payment in payments:
            try:
                payment.check_payment_status()
            except Exception as e:
                _logger.error(
                    "Failed to verify payment %d: %s",
                    payment.id,
                    str(e))
                payment.message_post(body=f"Verification failed: {str(e)}")

    def action_view_transactions(self):
        """Action to view payment transactions"""
        self.ensure_one()
        return {
            'name': _('Transactions'),
            'view_mode': 'tree,form',
            'res_model': 'monero.transaction',
            'type': 'ir.actions.act_window',
            'domain': [('payment_id', '=', self.id)],
            'context': {'default_payment_id': self.id}
        }

    def _get_status_alert_class(self):
        """Get Bootstrap alert class for current status"""
        self.ensure_one()
        return {
            'pending': 'info',
            'partial': 'warning',
            'paid_unconfirmed': 'warning',
            'confirmed': 'success',
            'expired': 'danger',
            'failed': 'danger',
            'overpaid': 'success'
        }.get(self.state, 'info')

    def _get_status_icon(self):
        """Get Font Awesome icon for current status"""
        self.ensure_one()
        return {
            'pending': 'fa-hourglass-half',
            'partial': 'fa-exclamation-circle',
            'paid_unconfirmed': 'fa-circle-notch fa-spin',
            'confirmed': 'fa-check-circle',
            'expired': 'fa-clock',
            'failed': 'fa-times-circle',
            'overpaid': 'fa-check-circle'
        }.get(self.state, 'fa-info-circle')

    def _get_status_message(self):
        """Get human-readable status message"""
        self.ensure_one()
        provider = self.env['payment.provider']._get_monero_provider()
        messages = {
            'pending': "Waiting for payment...",
            'partial': "Partial payment received (%.12f/%0.12f XMR)" % (
                self.amount_received, self.amount),
            'paid_unconfirmed': "Payment received (confirming... %d/%d confirmations)" % (
                self.confirmations, provider.confirmation_threshold),
            'confirmed': "Payment confirmed!",
            'expired': "Payment expired",
            'failed': "Payment failed: %s" % (self.error_message or "Unknown error"),
            'overpaid': "Payment received (overpaid)"
        }
        return _(messages.get(self.state, "Pending"))

    def get_expiry_time(self):
        """Get formatted remaining time until expiration"""
        self.ensure_one()
        if not self.expiration:
            return ""
            
        delta = self.expiration - fields.Datetime.now()
        if delta.total_seconds() <= 0:
            return "Expired"
            
        hours, remainder = divmod(delta.seconds, 3600)
        minutes = remainder // 60
        return f"{hours}h {minutes}m"

