from decimal import Decimal
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

# ================================
# pos_payment.py 
# ================================

class PosPaymentMethod(models.Model):
    """
    Point of Sale payment method extension for Monero RPC integration.
    
    Extends Odoo's POS payment methods to support Monero cryptocurrency
    payments with provider configuration, timeout settings, QR code generation,
    and currency conversion capabilities.
    
    :inherits: pos.payment.method
    
    **Key Features:**
    
    - Monero payment provider linkage
    - Automatic currency conversion to XMR
    - QR code generation for mobile wallets
    - Configurable payment timeouts
    - POS terminal integration
    
    .. note::
       This extension requires a configured Monero payment provider
       to function properly.
    
    .. versionadded:: 1.0
    """
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
        """
        Determine if the payment method uses Monero.
        
        Sets the ``is_monero`` flag based on whether the linked payment
        provider is configured for Monero RPC payments.
        
        **Logic:**
        
        ``is_monero = payment_provider_id.code == 'monero_rpc'``
        
        **Usage:**
        
        This computed field is used throughout the POS interface to:
        - Show/hide Monero-specific options
        - Apply Monero-specific validation
        - Route payments to appropriate handlers
        
        .. code-block:: python
        
           if payment_method.is_monero:
               # Handle Monero-specific logic
               pass
        """
        for method in self:
            method.is_monero = method.payment_provider_id.code == 'monero_rpc'

    def _get_payment_terminal_selection(self):
        """
        Extend the list of supported payment terminals to include Monero.
        
        Adds Monero RPC as a valid payment terminal option in the POS
        configuration interface.
        
        :returns: Extended list of terminal options including Monero
        :rtype: list[tuple]
        
        **Terminal Options:**
        
        Appends ``('monero_rpc', 'Monero RPC')`` to the existing terminal
        selection list, allowing users to configure Monero as a payment
        terminal in POS settings.
        
        .. note::
           This method extends the parent selection without modifying
           existing terminal options.
        """
        selection = super()._get_payment_terminal_selection()
        selection.append(('monero_rpc', 'Monero RPC'))
        return selection

    def _convert_to_xmr(self, amount, currency):
        """
        Convert fiat currency amount to Monero (XMR) equivalent.
        
        Performs real-time currency conversion using exchange rates from
        the configured payment provider to determine the XMR amount
        required for a given fiat payment.
        
        :param float amount: Fiat amount to convert
        :param str currency: Source currency code (e.g., 'USD', 'EUR')
        :returns: Equivalent amount in XMR
        :rtype: float
        :raises ValidationError: If no provider configured or conversion fails
        
        **Conversion Process:**
        
        1. Validate payment provider configuration
        2. Fetch current exchange rate for currency pair
        3. Calculate XMR equivalent: ``xmr_amount = fiat_amount / exchange_rate``
        4. Return converted amount
        
        **Example:**
        
        .. code-block:: python
        
           # Convert $100 USD to XMR
           xmr_amount = method._convert_to_xmr(100.0, 'USD')
           # If XMR = $200, result would be 0.5 XMR
        
        **Error Handling:**
        
        - Missing provider → ValidationError
        - Rate fetch failure → ValidationError with details
        - Network issues → Propagated as ValidationError
        
        .. seealso::
           :meth:`payment.provider._get_monero_exchange_rate` for rate fetching
        """
        self.ensure_one()
        if not self.payment_provider_id:
            raise ValidationError(_("No Monero payment provider configured"))

        try:
            rate = self.payment_provider_id.get_xmr_rate(currency)
            if not rate:
                raise ValidationError(_("Exchange rate unavailable for %s") % currency)
            return float(Decimal(str(amount)) / Decimal(str(rate)))
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(_("XMR conversion failed: %s") % str(e))

    @api.constrains('payment_provider_id', 'use_payment_terminal')
    def _check_monero_config(self):
        """
        Validate Monero payment method configuration.
        
        Ensures that when Monero RPC is selected as the payment terminal,
        a corresponding payment provider is properly configured.
        
        :raises ValidationError: If Monero terminal selected without provider
        
        **Validation Rules:**
        
        - If ``use_payment_terminal == 'monero_rpc'``
        - Then ``payment_provider_id`` must be set
        - Provider must be active and properly configured
        
        **Purpose:**
        
        Prevents runtime errors by ensuring proper configuration before
        the payment method can be used in POS operations.
        
        .. code-block:: python
        
           # This would trigger validation error:
           method.use_payment_terminal = 'monero_rpc'
           method.payment_provider_id = False  # Missing provider
        """
        for method in self:
            if method.use_payment_terminal == 'monero_rpc' and not method.payment_provider_id:
                raise ValidationError(_("Monero payment method requires a linked payment provider"))


class PosOrder(models.Model):
    """
    Point of Sale order extension for Monero payment integration.
    
    Extends POS orders to support Monero cryptocurrency payments with
    payment record linkage, status tracking, and QR-based payment processing.
    
    :inherits: pos.order
    
    **Enhanced Features:**
    
    - Direct Monero payment record association
    - Real-time payment status monitoring  
    - Confirmation count tracking
    - Automated payment processing workflow
    
    .. note::
       Monero payments are processed asynchronously, requiring status
       monitoring until sufficient confirmations are received.
    
    .. versionadded:: 1.0
    """
    _inherit = 'pos.order'

    monero_payment_id = fields.Many2one('monero.payment', string='Monero Payment')
    monero_payment_status = fields.Selection(related='monero_payment_id.state', string='Payment Status')
    monero_confirmations = fields.Integer(related='monero_payment_id.confirmations', string='Confirmations')

    def _create_monero_payment(self, amount):
        """
        Create a new Monero payment record for the POS order.
        
        Initializes a new payment record with order details and amount,
        setting up the foundation for cryptocurrency payment processing.
        
        :param float amount: Fiat amount to be paid
        :returns: Newly created Monero payment record
        :rtype: monero.payment
        
        **Payment Record Fields:**
        
        - ``amount``: Payment amount in fiat currency
        - ``currency``: Order currency (automatically converted to XMR)  
        - ``order_ref``: POS order reference for tracking
        - ``description``: Human-readable payment description
        
        **State Management:**
        
        The created payment starts in 'draft' state and progresses through:
        ``draft → pending → paid_unconfirmed → confirmed``
        
        .. code-block:: python
        
           # Create payment for $50 order
           payment = order._create_monero_payment(50.0)
           print(f"Payment created: {payment.order_ref}")
        
        .. seealso::
           :meth:`_process_monero_payment` for complete payment processing
        """
        self.ensure_one()
        provider = self.env['payment.provider'].search(
            [('code', '=', 'monero_rpc')], limit=1)
        if not provider:
            raise ValidationError(_("No Monero payment provider configured"))
        # Delegate to the provider which handles address generation and conversion
        return provider._create_monero_from_fiat_payment(
            self.pos_reference,
            amount,
            self.currency_id,
            None,
        )

    def _process_monero_payment(self, payment_method, amount):
        """
        Handle complete Monero payment flow and return QR payment information.
        
        Orchestrates the entire Monero payment process from creation to
        QR code generation, providing all necessary information for
        customer payment completion.
        
        :param payment_method: POS payment method configured for Monero
        :type payment_method: pos.payment.method
        :param float amount: Amount to be paid in fiat currency
        :returns: Payment metadata including address, amount, and QR URL
        :rtype: dict
        
        **Processing Workflow:**
        
        1. Create new Monero payment record
        2. Link payment to current POS order
        3. Generate payment address (subaddress or integrated)
        4. Calculate XMR amount using current exchange rates
        5. Generate QR code for mobile wallet scanning
        6. Return payment information for UI display
        
        **Response Structure:**
        
        .. code-block:: python
        
           {
               'payment_id': 123,
               'address': '4A1234...XYZ789',
               'amount': 0.25,  # XMR amount
               'currency': 'USD',  # Original currency
               'qr_code_url': '/monero/qr/123?size=200'
           }
        
        **QR Code Integration:**
        
        The generated QR code URL can be used directly in POS interfaces
        to display scannable payment codes for mobile wallet applications.
        
        .. note::
           This method modifies the order by linking the Monero payment
           record for status tracking purposes.
        """
        self.ensure_one()
        monero_payment = self._create_monero_payment(amount)
        self.write({'monero_payment_id': monero_payment.id})
        
        return {
            'payment_id': monero_payment.id,
            'address': monero_payment.address_seller,          # fix #67: use payment record field
            'amount_xmr': monero_payment.amount,               # fix #69: XMR amount
            'amount_fiat': amount,                             # original fiat amount
            'currency': self.currency_id.name,
            'qr_code_url': f"/monero/qr/{monero_payment.id}?size={payment_method.qr_size}"  # fix #68
        }

