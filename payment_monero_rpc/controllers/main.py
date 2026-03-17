import logging
import base64
from odoo import http, _, fields
from odoo.http import request, route
from werkzeug import urls
from odoo.exceptions import AccessError, ValidationError, UserError
from odoo.exceptions import MissingError
from odoo.addons.website_sale.controllers.main import WebsiteSale

try:
    from psycopg2.errors import LockNotAvailable
except ImportError:
    LockNotAvailable = Exception  # fallback for older psycopg2

_logger = logging.getLogger(__name__)

class MoneroWebsiteSale(WebsiteSale):
    """
    Extends WebsiteSale to add Monero payment handling.
    
    This controller provides comprehensive Monero cryptocurrency payment processing
    functionality for Odoo e-commerce websites, including payment validation,
    status checking, QR code generation, and invoice creation.
    
    :inherits: WebsiteSale
    :author: Your Name
    :version: 1.0
    """

    def _validate_order_access(self, order_id, access_token):
        """
        Enhanced order access validation with debug logging.
        
        Validates access to a sale order using the provided order ID and access token.
        This method provides enhanced validation with debug logging capabilities.
        
        :param int order_id: The ID of the sale order to validate
        :param str access_token: The access token for order verification
        :returns: Sale order record with sudo privileges
        :rtype: sale.order
        :raises AccessError: If order access is denied
        
        .. note::
           This method uses sudo() privileges to access the order record
        
        .. versionadded:: 1.0
        """
        import hmac as _hmac
        order_sudo = request.env['sale.order'].sudo().browse(order_id)
        if not order_sudo.exists():
            raise MissingError(_("Order not found"))
        if not order_sudo.access_token or not _hmac.compare_digest(
            order_sudo.access_token, access_token or ''
        ):
            raise AccessError(_("Invalid access token"))
        return order_sudo
                       
    def _validate_and_lock_order(self, order_id, access_token):
        """
        Validate order and acquire lock for payment processing.
        
        Performs comprehensive order validation including access token verification,
        order state checking, and database-level locking to prevent concurrent
        payment processing.
        
        :param int order_id: The ID of the sale order to validate and lock
        :param str access_token: The access token for order verification
        :returns: Validated sale order record with sudo privileges
        :rtype: sale.order
        :raises MissingError: If order is not found or access token is invalid
        :raises ValidationError: If order is cancelled or access token is invalid
        :raises UserError: If order is already paid or payment is being processed
        
        .. warning::
           This method acquires a database lock on the order record. Ensure
           proper exception handling to avoid deadlocks.
        
        .. code-block:: python
        
           try:
               order = self._validate_and_lock_order(order_id, token)
               # Process payment
           except ValidationError as e:
               # Handle validation errors
               pass
        """
        try:
            order_sudo = request.env['sale.order'].sudo().browse(order_id)
            # Issue 7: use hmac.compare_digest for constant-time comparison, consistent
            # with _validate_order_access. Direct != is susceptible to timing attacks.
            import hmac as _hmac
            if not order_sudo.exists() or not _hmac.compare_digest(
                order_sudo.access_token or '', access_token or ''
            ):
                raise MissingError(_("Order not found or invalid access token"))
            
            request.env.cr.execute(
                'SELECT 1 FROM sale_order WHERE id = %s FOR NO KEY UPDATE NOWAIT',
                (order_id,)
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
    def _process_monero_payment(self, order_id, **kwargs):
        """Core Monero payment processing logic."""
        access_token = kwargs.get('access_token', '')
        try:
            order = self._validate_order_access(order_id, access_token)
        except (AccessError, MissingError) as e:
            return {'success': False, 'error': str(e)}

        provider = request.env['payment.provider'].search([('code', '=', 'monero_rpc')], limit=1)
        if not provider:
            return {'success': False, 'error': 'Monero provider not configured'}

        payment = provider._create_monero_from_fiat_payment(
            order.name, order.amount_total, order.currency_id, order)

        currencyXmr = request.env['res.currency'].search([('name', '=', 'XMR')], limit=1)

        expiration_str = (
            payment.expiration.strftime("%Y-%m-%d %H:%M:%S")
            if payment.expiration else None
        )

        payment_data = {
            'id': payment.id,
            'address_seller': payment.address_seller,
            'amount_str': '%.12f' % payment.amount,
            'state': payment.state,
            'order_ref': order.name,
            'confirmations': payment.confirmations,
            'required_confirmations': provider.confirmation_threshold,
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
            'monero_symbol': currencyXmr.symbol if currencyXmr else 'XMR',
            'invoice_ids': order.invoice_ids.ids,
            'monero_uri': payment.qr_code_uri or '',
        }

        # Store in session as convenience cache only — payment_page reads DB directly
        request.session['monero_payment_data'] = payment_data

        return {
            "success": True,
            "payment": payment_data,
            "payment_id": payment_data["payment_id"],
        }

    @route('/shop/payment/monero/transaction', type='http', auth='public', website=True, csrf=True, methods=['GET'])
    def monero_payment_processor(self, **kwargs):
        """
        Process Monero payments and display payment page.
        
        HTTP endpoint that processes Monero payment requests and redirects
        to the appropriate payment page. Validates required parameters,
        creates payment records, and handles error scenarios.
        
        :param kwargs: HTTP request parameters
        :type kwargs: dict
        :returns: HTTP redirect response
        :rtype: werkzeug.wrappers.Response
        
        **Required Parameters:**
        
        * ``order_id`` (int): Sale order ID
        * ``access_token`` (str): Order access token
        * ``provider_id`` (int): Payment provider ID
        * ``amount`` (float): Payment amount
        
        **Success Flow:**
        
        1. Validate required parameters
        2. Verify order access
        3. Create Monero payment record
        4. Redirect to payment page
        
        **Error Handling:**
        
        * Missing parameters → redirect to error page
        * Invalid order access → redirect to error page
        * Processing errors → redirect to error page
        
        .. code-block:: http
        
           GET /shop/payment/monero/transaction?order_id=123&access_token=abc&provider_id=1&amount=100.00
        """
        try:
            required_params = ['order_id', 'access_token', 'provider_id', 'amount']
            if not all(k in kwargs for k in required_params):
                raise ValueError("Missing required parameters")

            order_id = int(kwargs['order_id'])
            access_token = kwargs['access_token']
            provider = request.env['payment.provider'].search([('code', '=', 'monero_rpc')], limit=1)

            # Issue 16: use _validate_order_access (consistent with rest of controller;
            # _verify_access_token may not exist in all Odoo 18 builds)
            order_sudo = self._validate_order_access(order_id, access_token)

            payment = provider._create_monero_from_fiat_payment(
                order_sudo.name, order_sudo.amount_total, order_sudo.currency_id, order_sudo)

            return request.redirect(f'/shop/payment/monero/page/{payment.id}')

        except Exception as e:
            # Issue 17: log the error before redirecting so production failures are debuggable
            _logger.error("monero_payment_processor failed: %s", str(e), exc_info=True)
            return request.redirect('/shop/payment/error?message=monero_processing_error')

    @route('/shop/payment/monero/status/<string:payment_id>', type='json', auth='public', website=True)
    def check_payment_status(self, payment_id, **kwargs):
        """
        Check payment status and confirmations.
        
        JSON endpoint that returns the current status of a Monero payment,
        including confirmation count, amounts, and expiration information.
        Used for real-time payment monitoring on the frontend.
        
        :param str payment_id: Unique payment identifier
        :param kwargs: Additional parameters (unused)
        :type kwargs: dict
        :returns: Payment status information or error details
        :rtype: dict
        
        **Success Response:**
        
        .. code-block:: python
        
           {
               'status': 'pending|confirmed|failed|expired',
               'status_message': 'Human readable message',
               'status_alert_class': 'success|warning|danger',
               'status_icon': 'fa-check|fa-clock|fa-times',
               'amount_received': 0.123456789,
               'amount_str': '0.123456789012',
               'required_amount': 0.123456789,
               'confirmations': 5,
               'required_confirmations': 5,
               'expired': False,
               'expiry_time_str': '2024-01-01 12:00:00'
           }
        
        **Error Response:**
        
        .. code-block:: python
        
           {
               'error': 'Error description',
               'status': 'error',
               'status_message': 'Error checking payment status',
               'status_alert_class': 'danger',
               'status_icon': 'fa-exclamation-circle'
           }
        
        .. note::
           This endpoint is called periodically by JavaScript to update
           payment status in real-time
        """
        provider = request.env['payment.provider'].sudo().search([('code', '=', 'monero_rpc')], limit=1)
        payment = request.env['monero.payment'].sudo().search([('payment_id', '=', payment_id)], limit=1)
        
        if not payment.exists():
            return {'error': 'Payment not found', 'status': 'error'}
            
        if not provider:
            return {'error': 'Provider not found', 'status': 'error'}
        
        try:
            result = payment.check_payment_status(payment_id)
            
            # Note (Issue 9): this endpoint returns 'status' (not 'state') for the payment
            # state value. JS consumers (payment_form_monero.js, payment_screen_monero.js)
            # read status.status. The model's check_payment_status() method returns 'state'
            # internally — the two shapes are intentionally different: model = internal,
            # controller = frontend API contract.
            return {
                'status': payment.state,
                'status_message': payment._get_status_message(),
                'status_alert_class': payment._get_status_alert_class(),
                'status_icon': payment._get_status_icon(),
                'amount_received': payment.amount_received,
                'amount_str': "%.12f" % payment.amount_received,
                'required_amount': payment.amount,
                'confirmations': payment.confirmations,
                'original_amount': payment.original_amount,
                'original_currency': payment.original_currency,
                'exchange_rate': payment.exchange_rate,
                'remaining_confirmations': max(0, provider.confirmation_threshold - payment.confirmations),
                'expired': payment.expiration < fields.Datetime.now(),
                'expiry_time_str': payment.expiration.strftime("%Y-%m-%d %H:%M:%S") if payment.expiration else None
            }
        except Exception as e:
            return {
                'error': str(e),
                'status': 'error',
                'status_message': "Error checking payment status",
                'status_alert_class': 'danger',
                'status_icon': 'fa-exclamation-circle'
            }

    @route('/shop/payment/monero/qr/<int:payment_id>', type='http', auth='public')
    def generate_qr_code(self, payment_id, access_token=None, **kwargs):
        """Generate Monero payment QR code — requires matching order access token."""
        payment = request.env['monero.payment'].sudo().browse(payment_id)
        if not payment.exists():
            return request.not_found()

        # Issue 81: enforce access control — caller must supply the order's token
        import hmac as _hmac
        order = payment.sale_order_id
        if order:
            if not access_token or not _hmac.compare_digest(
                order.access_token or '', access_token
            ):
                return request.not_found()
        elif not access_token:
            # No linked order — require token to be stored on the payment itself
            # (future: add a token field to monero.payment; for now, deny access)
            return request.not_found()

        try:
            if payment.image_qr:
                img_data = base64.b64decode(payment.image_qr)
            else:
                return request.not_found()

            return request.make_response(
                img_data,
                headers=[
                    ('Content-Type', 'image/png'),
                    ('Cache-Control', 'public, max-age=3600'),  # Issue 82
                ]
            )
        except Exception as e:
            _logger.error("QR serving failed: %s", str(e))
            return request.not_found()
            

    @route('/shop/payment/monero/page/<int:payment_id>', auth='public', website=True)
    def payment_page(self, payment_id, **kwargs):
        """Display payment page for customers."""
        payment = request.env['monero.payment'].sudo().browse(payment_id)
        if not payment.exists():
            return request.not_found()

        provider = request.env['payment.provider'].sudo().search(
            [('code', '=', 'monero_rpc')], limit=1)

        # Try session cache first; fall back to DB record (survives page refresh)
        payment_data = request.session.pop('monero_payment_data', None)
        if not payment_data or payment_data.get('id') != payment.id:
            payment_data = {
                'id': payment.id,
                'address_seller': payment.address_seller,
                'amount_str': '%.12f' % payment.amount,
                'state': payment.state,
                'order_ref': payment.order_ref,
                'confirmations': payment.confirmations,
                'required_confirmations': provider.confirmation_threshold if provider else 2,
                'payment_id': payment.payment_id,
                'image_qr': payment.image_qr,
                'expiry_time_str': (
                    payment.expiration.strftime("%Y-%m-%d %H:%M:%S")
                    if payment.expiration else None
                ),
            }

        return request.render('payment_monero_rpc.monero_payment_page', {
            'payment': payment_data,
            'monero_uri': payment.qr_code_uri or '',
            'is_dark': False,
        })

    @route('/shop/payment/monero/verify', type='json', auth='user', csrf=True)
    def verify_payments(self, payment_ids, **kwargs):
        """Bulk verification endpoint — requires authenticated user."""
        try:
            results = []
            for pid in payment_ids:
                payment = request.env['monero.payment'].sudo().search(
                    [('payment_id', '=', str(pid))], limit=1)
                if not payment or payment.state in ('confirmed', 'failed'):
                    continue
                result = payment.check_payment_status()
                results.append({
                    'payment_id': payment.payment_id,
                    'status': result.get('state'),
                    'amount_received': float(result.get('amount_received', 0)),
                    'confirmations': result.get('confirmations', 0),
                })
            return results
        except Exception as e:
            _logger.error("Bulk verification failed: %s", str(e))
            return {'error': str(e)}

    @route('/shop/payment/monero/invoice/<int:payment_id>', type='http', auth='public')
    def generate_invoice(self, payment_id, access_token=None, **kwargs):
        """Generate PDF invoice for payment (requires order access token)."""
        payment = request.env['monero.payment'].sudo().browse(payment_id)
        if not payment.exists():
            return request.not_found()

        # Ownership check: caller must supply the related sale order's access token
        # Issue 83: if there is no linked order, deny access (no authorisation path)
        order = payment.sale_order_id
        if not order:
            return request.not_found()
        import hmac as _hmac
        if not access_token or not _hmac.compare_digest(
            order.access_token or '', access_token
        ):
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
    def generate_proof(self, payment_id, access_token=None, **kwargs):
        """Generate payment proof PDF (requires order access token)."""
        payment = request.env['monero.payment'].sudo().browse(payment_id)
        if not payment.exists() or payment.state != 'confirmed':
            return request.not_found()

        # Ownership check: caller must supply the related sale order's access token
        # Issue 83: if there is no linked order, deny access (no authorisation path)
        order = payment.sale_order_id
        if not order:
            return request.not_found()
        import hmac as _hmac
        if not access_token or not _hmac.compare_digest(
            order.access_token or '', access_token
        ):
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
        """Return frontend translations. Uses Odoo's JS _t() system in Odoo 17+."""
        # ir.translation was removed in Odoo 17. Translations are now served via
        # the standard /web/webclient/translations endpoint using .po files and
        # the JavaScript _t() / _lt() helpers. This endpoint is a no-op stub kept
        # for backward compatibility with any external callers.
        _logger.debug("get_translations called for lang=%s (stub — use JS _t())", lang)
        return []
