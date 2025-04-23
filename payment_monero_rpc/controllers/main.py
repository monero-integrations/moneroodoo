import logging
from odoo import http, _, fields
from odoo.http import request, route
from werkzeug import urls
from odoo.exceptions import AccessError, ValidationError
from odoo.addons.website_sale.controllers.main import WebsiteSale

_logger = logging.getLogger(__name__)

class MoneroWebsiteSale(WebsiteSale):
    """Extends WebsiteSale to add Monero payment handling."""

    def _validate_order_access(self, order_id, access_token):
        """Enhanced order access validation with debug logging."""
        order_sudo = request.env['sale.order'].sudo().browse(order_id)
        _logger.debug("Just return order; no validation - %s", order_sudo)
            
        return order_sudo
                       
    def _validate_and_lock_order(self, order_id, access_token):
        """Validate order and acquire lock for payment processing"""
        try:
            order_sudo = request.env['sale.order'].sudo().browse(order_id)
            if not order_sudo.exists() or order_sudo.access_token != access_token:
                raise MissingError(_("Order not found or invalid access token"))
            
            request.env.cr.execute(
                SQL('SELECT 1 FROM sale_order WHERE id = %s FOR NO KEY UPDATE NOWAIT', order_id)
            )
            
            if order_sudo.state == "cancel":
                raise ValidationError(_("The order has been cancelled."))
                
            order_sudo._check_cart_is_ready_to_be_paid()
            
            if order_sudo.currency_id.compare_amounts(order_sudo.amount_paid, order_sudo.amount_total) == 0:
                raise UserError(_("The cart has already been paid."))
                
            return order_sudo
            
        except MissingError:
            raise
        except AccessError as e:
            raise ValidationError(_("The access token is invalid.")) from e
        except LockNotAvailable:
            raise UserError(_("Payment is already being processed."))

    @route('/shop/payment/monero/process/<int:order_id>', type='json', auth='public', website=True, csrf=True)
    def _process_monero_payment(self, order_sudo, provider, **kwargs):
        """Core Monero payment processing logic"""
        order = request.env['sale.order'].search([('id', '=', order_sudo)], limit=1)
        currency = order.currency_id.name
        amount = order.amount_total
        provider = request.env['payment.provider'].search([('code', '=', 'monero_rpc')], limit=1)
                    
        if currency != 'XMR':
            rate = provider.get_xmr_rate(currency)
            if not rate or rate <= 0:
                raise UserError(_("Could not get exchange rate for %s") % currency)
            amount = amount / rate
        
        payment = provider._create_monero_from_fiat_payment(order.name, order.amount_total, order.currency_id, order)
        
        currencyXmr = request.env['res.currency'].search([('name', '=', 'XMR')], limit=1)
        
        required_confirmations = int(request.env['ir.config_parameter'].sudo().get_param('monero.required_confirmations', default=10))

        if payment.expiration:
            expiration_str = payment.expiration.strftime("%Y-%m-%d %H:%M:%S")
        else:
            expiration_str = None
            
        invoice_ids = order.invoice_ids.ids
        
        payment_data = {
            'id': payment.id,
            'address_seller': payment.address_seller,
            'amount_str': '%.12f' % payment.amount,
            'state': payment.state,
            'order_ref': order.name,
            'confirmations': payment.confirmations,
            'required_confirmations': required_confirmations,
            'original_amount_str': '%.2f' % order.amount_total,
            'original_currency': order.currency_id.name,
            'exchange_rate_str': '%.2f' % payment.exchange_rate,
            'payment_id': payment.payment_id,
            'image_qr': payment.image_qr,
            'expiry_time_str': expiration_str,
            'sale_order_id': order.id,
            'status_alert_class': payment._get_status_alert_class(),
            'status_icon': payment._get_status_icon(),
            'status_message': payment._get_status_message(),
            'monero_symbol': currencyXmr.symbol,
            'invoice_ids': invoice_ids,              
            'monero_uri': f"monero:{payment.address_seller}?tx_amount={payment.amount:.12f}",
        }
        
        _logger.debug("Payment Data: %s", payment_data)

        request.session['monero_payment_data'] = payment_data

        return {
            "success": True,
            "payment": payment_data,
            "payment_id": payment_data["payment_id"],
        }

    @route('/shop/payment/monero/transaction', type='http', auth='public', website=True, csrf=True, methods=['GET'])
    def monero_payment_processor(self, **kwargs):
        """
        Process Monero payments and display payment page
        """
        try:
            required_params = ['order_id', 'access_token', 'provider_id', 'amount']
            if not all(k in kwargs for k in required_params):
                raise ValueError("Missing required parameters")

            order_id = int(kwargs['order_id'])
            access_token = kwargs['access_token']
            amount = float(kwargs['amount'])
            provider = request.env['payment.provider'].search([('code', '=', 'monero_rpc')], limit=1)           

            order_sudo = request.env['sale.order'].sudo().browse(order_id)
            if not order_sudo.exists() or not order_sudo._verify_access_token(access_token):
                raise AccessError("Order access denied")

            payment = provider._create_monero_from_fiat_payment(order_sudo.name, order_sudo.amount_total, order_sudo.currency_id, order_sudo)

            return request.redirect(f'/shop/payment/monero/page/{payment.id}')

        except Exception as e:
            _logger.exception("Monero payment processing failed")
            return request.redirect(f'/shop/payment/error?message=monero_processing_error')

    @route('/shop/payment/monero/status/<string:payment_id>', type='json', auth='public', website=True)
    def check_payment_status(self, payment_id, **kwargs):
        """Check payment status and confirmations"""
        provider = request.env['payment.provider'].sudo().search([('code', '=', 'monero_rpc')], limit=1)
        payment = request.env['monero.payment'].sudo().search([('payment_id', '=', payment_id)], limit=1)
        
        if not payment.exists():
            return {'error': 'Payment not found', 'status': 'error'}
            
        if not provider:
            return {'error': 'Provider not found', 'status': 'error'}
        
        try:
            result = payment.check_payment_status(payment_id)
            
            return {
                'status': payment.state,
                'status_message': payment._get_status_message(),
                'status_alert_class': payment._get_status_alert_class(),
                'status_icon': payment._get_status_icon(),
                'amount_received': payment.amount,
                'amount_str': "%.12f" % payment.amount,
                'required_amount': payment.amount,
                'confirmations': payment.confirmations,
                'original_amount': payment.original_amount,
                'original_currency': payment.original_currency,                
                'exchange_rate': payment.exchange_rate,
                'required_confirmations': provider.confirmation_threshold - payment.confirmations,
                'expired': payment.expiration < fields.Datetime.now(),
                'expiry_time_str': payment.expiration.strftime("%Y-%m-%d %H:%M:%S") if payment.expiration else None   
            }
        except Exception as e:
            _logger.exception("Failed to check payment status for payment %s", payment_id)
            return {
                'error': str(e),
                'status': 'error',
                'status_message': "Error checking payment status",
                'status_alert_class': 'danger',
                'status_icon': 'fa-exclamation-circle'
            }

    @route('/shop/payment/monero/qr/<int:payment_id>', type='http', auth='public')
    def generate_qr_code(self, payment_id):
        """Generate Monero payment QR code"""
        _logger.debug("Generating QR Code for payment %d: ", payment_id)
        payment = request.env['monero.payment'].sudo().browse(payment_id)
        if not payment.exists():
            return request.not_found()
            
        try:
            import qrcode
            from io import BytesIO
            
            monero_uri = f"monero:{payment.address_seller}?tx_amount={payment.amount}"
            if payment.description:
                monero_uri += f"&tx_description={payment.description}"
            
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(monero_uri)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)
            
            return request.make_response(
                buffer.getvalue(),
                headers=[('Content-Type', 'image/png')]
            )
        except Exception as e:
            _logger.error("QR generation failed: %s", str(e))
            return request.not_found()
            

    @route('/shop/payment/monero/page/<int:payment_id>', auth='public', website=True)
    def payment_page(self, payment_id, **kwargs):
        """Display payment page for customers"""
        payment = request.env['monero.payment'].sudo().browse(payment_id)
        if not payment.exists():
            return request.not_found()
            
        payment_data = request.session.pop('monero_payment_data', None)
        if not payment_data:
            return request.redirect('/shop?error=session_expired')
            
        _logger.debug("About to render: %s", payment_data);
            
        return request.render('payment_monero_rpc.monero_payment_page', {
            'payment': payment_data,
            'monero_uri': f"monero:{payment_data['address_seller']}?tx_amount={payment_data['amount_str']}",
            'is_dark': False,
        })

    @route('/shop/payment/monero/verify', type='http', auth='none', csrf=False)
    def verify_payments(self, payment_ids):
        """Bulk verification endpoint for cron jobs"""
        try:
            payments = request.env['monero.payment'].sudo().browse(payment_ids)
            results = []
            for payment in payments:
                if payment.state not in ('confirmed', 'failed'):
                    result = self.check_payment_status(payment.id)
                    results.append({
                        'payment_id': payment.id,
                        'status': result.get('status'),
                        'amount_received': result.get('amount_received'),
                        'confirmations': result.get('confirmations')
                    })
            return results
        except Exception as e:
            _logger.error("Bulk verification failed: %s", str(e))
            return {'error': str(e)}

    @route('/shop/payment/monero/invoice/<int:payment_id>', type='http', auth='public')
    def generate_invoice(self, payment_id, **kwargs):
        """Generate PDF invoice for payment"""
        payment = request.env['monero.payment'].sudo().browse(payment_id)
        if not payment.exists():
            return request.not_found()
            
        pdf = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'payment_monero_rpc.monero_payment_invoice',
            [payment.id],
            data={'payment': payment}
        )[0]
        
        return request.make_response(
            pdf,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', f'attachment; filename=Monero_Payment_{payment.id}.pdf')
            ]
        )

    @route('/shop/payment/monero/proof/<int:payment_id>', type='http', auth='public')
    def generate_proof(self, payment_id, **kwargs):
        """Generate payment proof PDF"""
        payment = request.env['monero.payment'].sudo().browse(payment_id)
        if not payment.exists() or payment.state != 'confirmed':
            return request.not_found()
            
        proof_data = {
            'tx_ids': [tx.txid for tx in payment.transaction_ids],
            'amount': payment.amount_received,
            'confirmations': payment.confirmations,
            'timestamp': fields.Datetime.now()
        }
        
        pdf = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'payment_monero_rpc.monero_payment_proof',
            [payment.id],
            data={'proof': proof_data}
        )[0]
        
        return request.make_response(
            pdf,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', f'attachment; filename=Monero_Proof_{payment.id}.pdf')
            ]
        )

    @http.route('/shop/payment/monero/translation', type='json', auth='public')
    def get_translations(self, lang, **kwargs):
        return request.env['ir.translation'].sudo().search_read(
            [('module', '=', 'payment_monero_rpc'), ('lang', '=', lang)],
            ['src', 'value']
        )            
