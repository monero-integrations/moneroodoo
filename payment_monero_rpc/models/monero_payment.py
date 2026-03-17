import logging
import secrets
import base64
import hashlib
import hmac
import json
from decimal import Decimal
from io import BytesIO
from datetime import datetime, timedelta

import qrcode
import urllib.parse

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

class MoneroPayment(models.Model):
    """Model for managing Monero cryptocurrency payments in Odoo.

    This model handles the creation, tracking, and processing of Monero payments,
    including integration with the Monero wallet RPC interface. It provides complete
    payment lifecycle management from creation to confirmation.

    The model supports both traditional Payment IDs and modern subaddresses for
    enhanced privacy and security. It automatically tracks payment status through
    blockchain confirmations and integrates with Odoo's sale order workflow.

    Attributes
    ----------
    _name : str
        Odoo model name ('monero.payment')
    _description : str
        Model description ('Monero Payments')
    _order : str
        Default ordering ('create_date desc')
    _inherit : list
        Inherited models (mail.thread, mail.activity.mixin)

    Examples
    --------
    Create a new Monero payment:

    >>> payment = env['monero.payment'].create({
    ...     'payment_id': 12345,
    ...     'amount': 0.1,
    ...     'address_seller': '4...',
    ...     'order_ref': 'SO001'
    ... })

    Check payment status:

    >>> status = payment.check_payment_status(payment.payment_id)
    >>> print(status['state'])
    """

    _name = 'monero.payment'
    _description = 'Monero Payments'
    _order = 'create_date desc'
    _rec_name = 'payment_ref'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    payment_ref = fields.Char(
        string="Reference",
        compute='_compute_payment_ref',
        store=True,
        help="Human-readable payment reference combining order and amount"
    )
    
    payment_id = fields.Char(
        string="Payment ID",
        required=True,
        readonly=True,
        index=True,
        help="Unique identifier for tracking this payment on the blockchain"
    )
    
    sale_order_id = fields.Many2one(
        'sale.order',
        string="Sales Order",
        readonly=True,
        index=True,
        help="Related Odoo sales order if payment is part of e-commerce flow"
    )
    
    address_seller = fields.Char(
        string="Receiving Address",
        readonly=True,
        required=True,
        help="Monero address where payment should be sent (subaddress or integrated address)"
    )
    
    address_buyer = fields.Char(
        string="Buyer Address",
        help="Optional buyer's Monero address for refund purposes"
    )
    
    subaddress_index = fields.Integer(
        string="Subaddress Index",
        readonly=True,
        help="Index of the subaddress if using subaddress-based payments"
    )
    
    amount = fields.Float(
        string="Amount (XMR)",
        required=True,
        digits=(16, 12),
        help="Expected payment amount in Monero (XMR). "
             "NOTE: stored as IEEE 754 double (~15 significant digits). "
             "Sub-piconero rounding is possible at high precision. "
             "Future improvement: store as Integer piconeros (1 XMR = 1e12 piconeros)."
    )
    
    amount_received = fields.Float(
        string="Amount Received (XMR)",
        readonly=True,
        digits=(16, 12),
        default=0.0,
        help="Actual amount received on the blockchain. "
             "NOTE: IEEE 754 double precision — sub-piconero rounding possible."
    )
    
    amount_due = fields.Float(
        string="Amount Due (XMR)",
        compute='_compute_amount_due',
        digits=(16, 12),
        help="Remaining amount to be paid (calculated field). "
             "NOTE: IEEE 754 double precision — sub-piconero rounding possible."
    )
    
    currency = fields.Char(
        string="Currency",
        default="XMR",
        required=True,
        readonly=True,
        help="Payment currency (always XMR for Monero payments)"
    )
    
    order_ref = fields.Char(
        string="Order Reference",
        index=True,
        help="External order reference for correlation with other systems"
    )
    
    description = fields.Text(
        string="Description",
        help="Free-text description of the payment purpose"
    )
    
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('pending', 'Pending Payment'),
            ('partial', 'Partially Paid'),
            ('paid_unconfirmed', 'Paid (Unconfirmed)'),
            ('confirmed', 'Confirmed'),
            ('expired', 'Expired'),
            ('failed', 'Failed'),
            ('overpaid', 'Overpaid')
        ],
        string='Status',
        default='draft',
        readonly=True,
        index=True,
        tracking=True,
        help="Current payment status based on blockchain confirmations"
    )
    
    confirmations = fields.Integer(
        string="Confirmations",
        readonly=True,
        compute='_compute_confirmations',
        store=False,  # Issue 3: monero_transaction.confirmations is store=False;
                      # a cross-model @api.depends on a non-stored field will not
                      # trigger stored recomputation. Compute live on every read.
        help="Number of blockchain confirmations for this payment"
    )
    
    expiration = fields.Datetime(
        string="Expiration Date",
        required=True,
        default=lambda self: fields.Datetime.now() + timedelta(hours=1),
        help="When this payment request expires if not completed"
    )
    
    create_date = fields.Datetime(
        string="Creation Date",
        readonly=True,
        help="Timestamp when this payment record was created"
    )
    
    error_message = fields.Text(
        string="Error Message",
        readonly=True,
        help="Error details if payment processing failed"
    )
    
    transaction_ids = fields.One2many(
        'monero.transaction',
        'payment_id',
        string="Transactions",
        help="Related blockchain transactions for this payment"
    )
    
    original_amount = fields.Float(
        string="Original Amount",
        digits=(16, 2),
        help="Original payment amount in fiat currency before XMR conversion. "
             "NOTE: IEEE 754 double precision."
    )
    
    original_currency = fields.Char(
        string="Original Currency",
        default="USD",
        help="Original fiat currency before conversion to XMR"
    )
    
    exchange_rate = fields.Float(
        string="Exchange Rate",
        digits=(16, 6),
        help="Exchange rate used to convert from original currency to XMR. "
             "NOTE: IEEE 754 double precision — minor rounding possible at 6+ decimals."
    )
    
    image_qr = fields.Binary(
        string="QR Code",
        compute='_compute_qr_code',
        store=True,
        help="Base64-encoded QR code image for payment"
    )
    
    last_check = fields.Datetime(
        string="Last checked",
        help="Timestamp of last blockchain status check"
    )
    
    qr_code_uri = fields.Char(
        string="Monero URI",
        compute='_compute_qr_code_uri',
        help="Monero URI for QR code generation following monero: protocol"
    )
    
    is_subaddress = fields.Boolean(
        string="Uses Subaddress",
        default=True,
        readonly=True,
        help="True if using modern subaddresses, False if using legacy Payment IDs"
    )

    _sql_constraints = [
        ('payment_id_unique', 'UNIQUE(payment_id)', 'Payment ID must be unique!'),
        ('amount_positive', 'CHECK(amount > 0)', 'Amount must be positive!'),
    ]

    @api.depends('order_ref', 'amount', 'currency')
    def _compute_payment_ref(self):
        """Compute the display name for the payment record."""
        for payment in self:
            payment.payment_ref = f"{payment.order_ref or 'Payment'} - {payment.amount:.12f} {payment.currency}"

    @api.depends('amount', 'amount_received')
    def _compute_amount_due(self):
        """Compute the remaining amount due for the payment.

        Calculated as max(0, amount - amount_received) to avoid negative values
        when payments are overpaid.

        Notes
        -----
        This field is automatically recalculated whenever amount_received changes,
        typically during payment status checks.
        """
        for payment in self:
            payment.amount_due = max(0.0, payment.amount - payment.amount_received)

    @api.depends('transaction_ids.confirmations')
    def _compute_confirmations(self):
        """Compute the minimum number of confirmations across all transactions.

        Uses the transaction with the fewest confirmations as the overall
        confirmation count, since all transactions must be sufficiently
        confirmed for the payment to be considered secure.

        Returns
        -------
        int
            Minimum confirmations across all related transactions, or 0 if no transactions
        """
        for payment in self:
            if not payment.transaction_ids:
                payment.confirmations = 0
            else:
                payment.confirmations = min(
                    (tx.confirmations for tx in payment.transaction_ids
                     if tx.confirmations is not None),
                    default=0
                )

    @api.depends('address_seller', 'amount', 'payment_id', 'order_ref')
    def _compute_qr_code_uri(self):
        """Generate a Monero URI for QR code generation.

        The URI follows the Monero payment URI standard (monero:) including:
        - Recipient address
        - Payment amount (tx_amount)
        - Payment ID (tx_payment_id)
        - Description (tx_description)

        The generated URI can be encoded into QR codes for easy payment
        by mobile Monero wallets.

        Format
        ------
        monero:{address}?tx_amount={amount}&tx_payment_id={id}&tx_description={desc}

        Examples
        --------
        For a payment with address "4ABC..." and amount 0.1:
        "monero:4ABC...?tx_amount=0.100000000000&tx_payment_id=12345&tx_description=Order SO001"
        """
        for payment in self:
            if payment.address_seller:
                desc = f"Order {payment.order_ref}" if payment.order_ref else "Payment"
                uri = (
                    f"monero:{payment.address_seller}"
                    f"?tx_amount={payment.amount:.12f}"
                )
                if not payment.is_subaddress:
                    uri += f"&tx_payment_id={payment.payment_id}"
                uri += f"&tx_description={urllib.parse.quote(desc)}"
                payment.qr_code_uri = uri
            else:
                payment.qr_code_uri = False

    @api.depends('qr_code_uri')
    def _compute_qr_code(self):
        """Generate a QR code image from the Monero URI.

        Creates a QR code using the qrcode library with error correction level L
        and encodes it as a base64 PNG image for display in Odoo web interface.

        The QR code parameters are optimized for mobile wallet scanning:
        - Version 1 (auto-sizing)
        - Error correction level M (medium, 15% recovery)
        - Box size 10 pixels
        - Border 4 modules

        Notes
        -----
        The resulting base64 string can be directly used in HTML img src attributes
        with data:image/png;base64, prefix.
        """
        for payment in self:
            if payment.qr_code_uri:
                qr = qrcode.QRCode(
                    version=None,
                    error_correction=qrcode.constants.ERROR_CORRECT_M,
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
    def create(self, vals_list):
        """Create new Monero payment record(s).

        Automatically generates a random payment ID if none is provided.
        """
        for vals in vals_list:
            if not vals.get('payment_id'):
                vals['payment_id'] = secrets.token_hex(32)
        return super().create(vals_list)

    @api.model
    def _get_current_block_height(self):
        """Get the current blockchain height from the Monero daemon.

        Connects to the configured Monero daemon to retrieve the current
        blockchain height, which is used for confirmation calculations
        and transaction verification.

        Returns
        -------
        int
            Current blockchain height, or 0 if unable to connect

        Raises
        ------
        Exception
            If connection to Monero daemon fails

        Notes
        -----
        This method is used internally by payment verification processes
        to determine how many confirmations a transaction has received.
        """
        provider = self.env['payment.provider']._get_monero_provider()
        try:
            daemon = provider._get_daemon()
            return daemon.height()
        except Exception as e:
            _logger.error("Failed to get block height: %s", str(e))
            return 0

    def refresh_exchange_rate(self):
        """Refresh the exchange rate for this payment.

        Fetches the current exchange rate for the original currency
        and updates the payment record. This is useful for payments
        that may need rate updates due to market volatility.

        Returns
        -------
        bool
            True if rate was successfully updated, False otherwise

        Examples
        --------
        >>> payment = env['monero.payment'].browse(123)
        >>> if payment.refresh_exchange_rate():
        ...     print(f"New rate: {payment.exchange_rate}")
        """
        self.ensure_one()
        provider = self.env['payment.provider']._get_monero_provider()
        try:
            rate = provider.get_xmr_rate(self.original_currency)
            if rate:
                self.exchange_rate = rate
                return True
        except Exception as e:
            _logger.error("Failed to fetch exchange rate: %s", str(e))
        return False
        
    def serialize_transfer(self, transfer):
        """Serialize a Monero transfer object to a dictionary.

        Converts complex Monero transfer objects into JSON-serializable
        dictionaries for storage or API responses. Handles type conversion
        for Decimal amounts, datetime objects, and other complex types.

        Parameters
        ----------
        transfer : object
            Monero transfer object from the python-monero library

        Returns
        -------
        dict
            Dictionary containing serialized transfer data with the following
            type conversions:
            - Decimal -> float
            - datetime -> ISO format string  
            - Other objects -> string representation

        Examples
        --------
        >>> transfer = wallet.incoming()[0]  # Get a transfer
        >>> data = payment.serialize_transfer(transfer)
        >>> print(data['amount'])  # Now a float instead of Decimal
        """
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

    def check_payment_status(self, paymentId=None):
        """Check payment status for a specific payment ID.

        Connects to the Monero wallet RPC to check for incoming transfers,
        updates payment state based on amount received and confirmations,
        and creates transaction records for any new payments found.

        This is the core method for payment verification and should be called
        periodically via cron jobs or manually by users checking payment status.

        Parameters
        ----------
        paymentId : str or int, optional
            The payment ID to check status for. If None, uses self.payment_id

        Returns
        -------
        dict
            Dictionary containing payment status with keys:
            
            - **state** (str): Current payment state ('pending', 'confirmed', etc.)
            - **amount_received** (Decimal): Total amount received 
            - **confirmations** (int): Number of blockchain confirmations
            - **transactions** (list): List of transaction details
            - **error** (str): Error message if applicable

        Raises
        ------
        UserError
            If payment record not found or RPC connection fails

        Notes
        -----
        Payment states are determined as follows:
        
        - **pending**: No payment received yet
        - **partial**: Some payment received but less than expected
        - **paid_unconfirmed**: Full payment received but insufficient confirmations
        - **confirmed**: Full payment received with sufficient confirmations  
        - **overpaid**: More than expected amount received
        - **error**: Processing error occurred

        The confirmation threshold is configurable via the payment provider settings.

        Examples
        --------
        Check payment status:

        >>> payment = env['monero.payment'].browse(123)
        >>> status = payment.check_payment_status()
        >>> if status['state'] == 'confirmed':
        ...     print("Payment confirmed!")

        Check by payment ID:

        >>> status = payment.check_payment_status(12345)
        >>> print(f"Received: {status['amount_received']} XMR")
        """
        self.ensure_one()

        # Issue 24: guard terminal states — never regress a confirmed/failed payment
        if self.state in ('confirmed', 'expired', 'failed'):
            return {
                'state': self.state,
                'amount_received': Decimal(str(self.amount_received)),
                'confirmations': self.confirmations,
                'transactions': []
            }

        if paymentId is None:
            paymentId = self.payment_id

        try:
            # Issue 22: acquire row-level lock to prevent concurrent double-confirmation
            self.env.cr.execute(
                'SELECT 1 FROM monero_payment WHERE id = %s FOR UPDATE NOWAIT',
                (self.id,)
            )

            provider = self.env['payment.provider']._get_monero_provider()
            if not provider:
                raise UserError(_("No Monero payment provider configured. Cannot check payment status."))
            wallet = provider._get_wallet_client()

            # Issue 21: filter at the RPC level by subaddress index when possible;
            # fall back to full scan filtered in Python only when necessary.
            if self.is_subaddress and self.subaddress_index:
                try:
                    all_incoming = wallet.incoming(
                        account=0, subaddr=self.subaddress_index
                    )
                    filtered = list(all_incoming)
                except TypeError:
                    # Library version doesn't support keyword filtering — fall back
                    all_incoming = wallet.incoming()
                    filtered = [
                        t for t in all_incoming
                        if getattr(t, "local_address", None) == self.address_seller
                    ]
            else:
                all_incoming = wallet.incoming()
                filtered = [
                    t for t in all_incoming
                    if getattr(t, "local_address", None) == self.address_seller
                ]

            transactions = []
            total_received = Decimal('0.0')

            # Process each matching transfer
            for transfer in filtered:
                try:
                    transaction = transfer.transaction

                    # Safely extract subaddress index using named tuple fields
                    subaddr_index = None
                    if hasattr(transfer, 'subaddr_index') and transfer.subaddr_index is not None:
                        if hasattr(transfer.subaddr_index, 'minor'):
                            subaddr_index = transfer.subaddr_index.minor
                        elif isinstance(transfer.subaddr_index, (list, tuple)) and len(transfer.subaddr_index) > 1:
                            subaddr_index = transfer.subaddr_index[1]
                        elif isinstance(transfer.subaddr_index, int):
                            subaddr_index = transfer.subaddr_index

                    # Safely convert amounts to avoid precision issues
                    transfer_amount = Decimal(str(getattr(transfer, 'amount', 0)))
                    transaction_fee = Decimal(str(getattr(transaction, 'fee', 0) or 0))

                    tx_data = {
                        'txid': getattr(transaction, 'hash', ''),
                        'amount': float(transfer_amount),
                        'fee': float(transaction_fee),
                        'block_height': getattr(transaction, 'height', None),
                        'timestamp': getattr(transaction, 'timestamp', None) or fields.Datetime.now(),
                        'confirmations': getattr(transaction, 'confirmations', 0),
                        'payment_id': self.id,
                        'payment_type': 'in',
                        'account_index': getattr(transfer, 'account_index', None),
                        'subaddr_index': subaddr_index,
                        'local_address': getattr(transfer, 'local_address', None),
                        'note': getattr(transaction, 'note', ''),
                        'tx_key': getattr(transaction, 'key', None),
                        'double_spend_seen': getattr(transaction, 'double_spend_seen', False),
                        'in_pool': getattr(transaction, 'in_pool', False),
                        'extra': str(getattr(transaction, 'extra', '')),
                        'stealth_address': getattr(transfer, 'stealth_address', None),
                    }

                    transactions.append(tx_data)
                    total_received += transfer_amount

                except Exception as e:
                    _logger.error("Error processing transfer: %s", e)
                    continue

            # Convert to float for comparison, using consistent precision
            amount_received_float = float(total_received)
            amount_expected_float = float(Decimal(str(self.amount)))

            amount_compare = float_compare(
                amount_received_float,
                amount_expected_float,
                precision_digits=12
            )

            # Issue 25: use the ORM computed field (minimum across all txs) rather
            # than breaking on the first confirmed individual transfer.
            # Re-read after upsert so computed field reflects new transactions.
            self.invalidate_recordset(['confirmations'])
            all_confirmed = (
                self.confirmations >= provider.confirmation_threshold
                and amount_compare == 0
            )
            new_state = (
                'confirmed'        if all_confirmed
                else 'overpaid'    if amount_compare == 1       # more received than expected — check BEFORE partial
                else 'paid_unconfirmed' if amount_compare == 0
                else 'partial'     if total_received > 0
                else 'pending'
            )
            confirmed = all_confirmed

            # Upsert transaction records — never wipe history
            for tx_data in transactions:
                existing = self.env['monero.transaction'].search(
                    [('txid', '=', tx_data['txid'])], limit=1)
                if not existing:
                    self.env['monero.transaction'].create(tx_data)
                else:
                    existing.write({k: v for k, v in tx_data.items()
                                    if k not in ('txid', 'payment_id')})

            # Calculate max confirmations safely
            max_confirmations = max(
                (tx.get('confirmations', 0) for tx in transactions), default=0)

            update_vals = {
                'amount_received': float(total_received),
                'state': new_state,
                'last_check': fields.Datetime.now(),
            }

            if confirmed:
                # Issue 23: _payment_confirmed is an instance method — do NOT pass self as arg
                self._payment_confirmed({**update_vals})
            else:
                self.write(update_vals)

            _logger.info(
                "Payment status updated - State: %s, Received: %s, Expected: %s, Confirmations: %d",
                new_state, amount_received_float, amount_expected_float, max_confirmations)

            return {
                'state': new_state,
                'amount_received': total_received,
                'confirmations': max_confirmations,
                'transactions': transactions
            }

        except Exception as e:
            _logger.error("Payment check failed: %s", str(e), exc_info=True)
            self._handle_rpc_error(str(e))
            raise            
            
    def generate_payment_proof(self):
        """Generate cryptographic proof of payment.

        Creates a cryptographically signed proof that this payment was completed,
        including all relevant transaction details and a verification signature.
        The proof is saved as a JSON attachment to the payment record.

        Returns
        -------
        dict
            Dictionary containing:
            
            - **proof** (dict): Complete payment proof data including:
              
              - payment_id: The payment identifier
              - address: Receiving address  
              - amount: Amount received
              - confirmations: Confirmation count
              - tx_hashes: List of transaction hashes
              - timestamp: Proof generation time
              - block_height: Minimum block height
              - signature: Cryptographic signature
              
            - **attachment_id** (int): ID of created attachment record

        Raises
        ------
        UserError
            If payment is not in confirmed state or proof system not configured

        Notes
        -----
        The proof system uses SHA256 hashing with a configurable private key
        to create tamper-evident payment records. The private key should be
        configured via system parameters: 'monero.payment_proof_key'

        Examples
        --------
        >>> payment = env['monero.payment'].browse(123)
        >>> if payment.state == 'confirmed':
        ...     proof = payment.generate_payment_proof()
        ...     print(f"Proof saved as attachment {proof['attachment_id']}")
        """
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_("Payment must be confirmed to generate proof"))
            
        proof_data = {
            'payment_id': self.payment_id,
            'address': self.address_seller,
            'amount': str(Decimal(str(self.amount_received))),
            'confirmations': self.confirmations,
            'tx_hashes': [tx.txid for tx in self.transaction_ids],
            'timestamp': fields.Datetime.now().isoformat(),
            'block_height': min(
                (tx.block_height for tx in self.transaction_ids if tx.block_height),
                default=0
            ),
            'signature': self._generate_signature(),
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
        """Generate cryptographic signature for payment proof.

        Creates a SHA256 hash signature using payment data and a private key
        for proof verification. The signature ensures the payment proof
        cannot be tampered with without detection.

        Returns
        -------
        str
            SHA256 hash of payment data concatenated with private key

        Raises
        ------
        UserError
            If private key is not configured in system parameters

        Notes
        -----
        The signature is generated from: payment_id + amount_received + address + private_key
        The private key must be configured in ir.config_parameter with key 'monero.payment_proof_key'
        """
        private_key = self.env['ir.config_parameter'].sudo().get_param(
            'monero.payment_proof_key')
        if not private_key:
            raise UserError(_("Payment proof system not configured - missing private key"))

        # Issue 31: use Decimal string representation to avoid float non-determinism
        # Issue 32: key is in ir.config_parameter (plaintext). In production, move to
        # an environment variable and read via os.environ.get('MONERO_PROOF_KEY').
        amount_str = Decimal(str(self.amount_received)).normalize()
        data = f"{self.payment_id}:{amount_str}:{self.address_seller}"
        return hmac.HMAC(
            private_key.encode(), data.encode(), digestmod=hashlib.sha256
        ).hexdigest()

    def _payment_confirmed(self, values):
        """Handle confirmed payment and trigger related actions.

        Called when a payment reaches confirmed status. Writes the final
        state, links the Odoo payment.transaction, confirms the sale order
        (without re-sending the order confirmation email — that is handled
        by _send_order_confirmation_mail via the transaction), and posts
        a chatter message.

        Parameters
        ----------
        values : dict
            Values to write to this payment record (state, amount_received, etc.)
        """
        try:
            self.write(values)

            if self.sale_order_id:
                # Issue 34: search by reference field on payment.transaction, not
                # by payment_id (which is a Many2one to payment.payment, not monero.payment)
                tx = self.env['payment.transaction'].sudo().search([
                    ('reference', '=', self.order_ref)
                ], limit=1)
                if tx:
                    tx._set_done()
                    # Issue 33: do NOT call _send_order_confirmation_mail here —
                    # action_confirm with send_email=True already sends it below.

                order = self.sale_order_id
                try:
                    if order.state in ['draft', 'sent']:
                        # Issue 33: use send_email=False to avoid double email;
                        # the tx confirmation email (email_template_payment_confirmed)
                        # is sent separately below.
                        order.with_context(send_email=False).action_confirm()
                    elif order.state == 'sale':
                        # Issue 36: use %s logging, not f-strings
                        _logger.info("Order %s is already confirmed", self.order_ref)
                    else:
                        _logger.warning(
                            "Order %s is in unexpected state %s",
                            self.order_ref, order.state
                        )
                except Exception as e:
                    _logger.error("Failed to confirm order %s: %s", self.order_ref, str(e))

            # Send single confirmation email via the payment record template
            template = self.env.ref(
                'payment_monero_rpc.email_template_payment_confirmed', raise_if_not_found=False
            )
            if template:
                template.send_mail(self.id, force_send=True)

            self.message_post(body=_(
                "Payment confirmed with %(conf)d confirmations. "
                "Amount received: %(amount)f XMR"
            ) % {'conf': self.confirmations, 'amount': self.amount_received})
        except Exception as e:
            _logger.error("Payment confirmation failed: %s", str(e))
            raise

    def _handle_rpc_error(self, error_message):
        """Handle RPC errors by updating payment state.

        Called when RPC communication with Monero wallet/daemon fails.
        Updates the payment record to reflect the error state and stores
        the error message for debugging.

        Parameters
        ----------
        error_message : str
            Error message to store in the payment record for troubleshooting

        Notes
        -----
        Sets payment state to 'failed' and records the timestamp of the error.
        This helps distinguish between temporary network issues and persistent
        configuration problems.
        """
        self.write({
            'error_message': error_message,
            'state': 'failed',
            'last_check': fields.Datetime.now()
        })

    @api.model
    def _cron_check_expired_payments(self):
        """Mark expired payments via scheduled cron job.

        Automated job that runs periodically to identify payments that have
        passed their expiration date without being completed. Updates their
        state to 'expired' to prevent further processing.

        This cron job should be configured to run regularly (e.g., every hour)
        to ensure timely cleanup of expired payment requests.

        Notes
        -----
        Only affects payments in 'pending' or 'partial' states that have
        passed their expiration datetime. Confirmed or failed payments
        are not affected.

        The number of expired payments is logged for monitoring purposes.

        Examples
        --------
        Configure in Odoo cron jobs:

        >>> # XML data file
        >>> <record id="cron_check_expired" model="ir.cron">
        ...     <field name="name">Check Expired Monero Payments</field>
        ...     <field name="model_id" ref="model_monero_payment"/>
        ...     <field name="code">model._cron_check_expired_payments()</field>
        ...     <field name="interval_number">1</field>
        ...     <field name="interval_type">hours</field>
        ... </record>
        """
        # Issue 37: do NOT expire paid_unconfirmed payments — the funds arrived on-chain
        # and we just need to wait for confirmations. Expiring them would alarm the customer.
        expired = self.search([
            ('state', 'in', ['pending', 'partial']),
            ('expiration', '<', fields.Datetime.now())
        ])
        expired.write({'state': 'expired'})
        _logger.info("Marked %d payments as expired", len(expired))

    @api.model
    def _cron_update_payment_rates(self):
        """Update exchange rates for pending payments via cron job.

        Scheduled job that refreshes exchange rates for payments with
        non-XMR original currencies. This helps maintain accurate conversion
        rates for pending fiat-to-XMR payments during market volatility.

        Should be run regularly (e.g., every 15-30 minutes) during business
        hours to keep rates current for pending payments.

        Notes
        -----
        Only processes payments in 'pending' or 'partial' states that have
        an original_currency different from 'XMR'. Confirmed payments are
        not updated since their rates should remain fixed.

        Errors updating individual payments are logged but don't stop
        processing of other payments.

        Examples
        --------
        Configure as cron job:

        >>> # This will update all pending USD/EUR payments with current rates
        >>> env['monero.payment']._cron_update_payment_rates()
        """
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
        """Verify pending payments via scheduled cron job.

        Core scheduled job that checks pending payments for incoming funds
        by querying the Monero blockchain. This is the main automation that
        detects when payments are received and confirmed.

        Processes payments in batches to avoid overwhelming the RPC connection
        and only checks payments that haven't expired yet.

        Notes
        -----
        This is the most important cron job for the payment system. It should
        run frequently (every 1-5 minutes) to provide responsive payment detection.

        Processing is batched to 100 payments per run to prevent timeouts.
        Only payments in active states ('pending', 'partial', 'paid_unconfirmed')
        that haven't expired are checked.

        Individual payment check failures are logged but don't stop the batch
        processing. Failed payments get error messages posted to their records.

        Performance Considerations
        --------------------------
        - RPC calls are made for each payment address
        - Blockchain queries may take several seconds each  
        - Consider reducing frequency during low-traffic periods
        - Monitor RPC connection limits and timeouts

        Examples
        --------
        Recommended cron configuration:

        >>> # Check every 2 minutes during business hours
        >>> <record id="cron_verify_payments" model="ir.cron">
        ...     <field name="name">Verify Monero Payments</field>
        ...     <field name="model_id" ref="model_monero_payment"/>
        ...     <field name="code">model._cron_verify_pending_payments()</field>
        ...     <field name="interval_number">2</field>
        ...     <field name="interval_type">minutes</field>
        ... </record>
        """
        payments = self.search([
            ('state', 'in', ['pending', 'partial', 'paid_unconfirmed']),
            ('expiration', '>', fields.Datetime.now())
        ], limit=100, order='last_check asc nulls first')
        
        _logger.info("Checking %d pending payments...", len(payments))
        for payment in payments:
            try:
                payment.check_payment_status()
            except Exception as e:
                _logger.error(
                    "Failed to verify payment %d: %s",
                    payment.id,
                    str(e))
                payment.message_post(body=_("Verification failed: %s") % str(e))

    def action_view_transactions(self):
        """Action to view payment transactions.

        Odoo window action that opens a view showing all blockchain transactions
        related to this payment. Useful for detailed transaction analysis and
        debugging payment issues.

        Returns
        -------
        dict
            Odoo window action definition containing:
            
            - **name**: Window title  
            - **view_mode**: View types available ('tree,form')
            - **res_model**: Target model ('monero.transaction')
            - **type**: Action type ('ir.actions.act_window')
            - **domain**: Filter for this payment's transactions
            - **context**: Default values for new records

        Examples
        --------
        Called from payment form view button:

        >>> # In XML view definition
        >>> <button name="action_view_transactions" 
        ...         string="View Transactions"
        ...         type="object"
        ...         class="btn-primary"/>

        Or programmatically:

        >>> payment = env['monero.payment'].browse(123)
        >>> action = payment.action_view_transactions()
        >>> # Returns action dict for opening transaction view
        """
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
        """Get Bootstrap alert class for current payment status.

        Returns the appropriate Bootstrap CSS class for displaying
        the payment status with proper color coding in web interfaces.

        Returns
        -------
        str
            Bootstrap alert class name:
            
            - **'success'**: For confirmed/overpaid payments (green)
            - **'warning'**: For partial/unconfirmed payments (yellow) 
            - **'danger'**: For expired/failed payments (red)
            - **'info'**: For pending payments (blue)

        Examples
        --------
        >>> payment = env['monero.payment'].browse(123)
        >>> css_class = payment._get_status_alert_class()
        >>> # Use in template: <div class="alert alert-{{ css_class }}">
        """
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
        """Get Font Awesome icon for current payment status.

        Returns the appropriate Font Awesome icon class for displaying
        alongside the payment status in user interfaces.

        Returns
        -------
        str
            Font Awesome icon class name:
            
            - **'fa-check-circle'**: Confirmed/overpaid (checkmark)
            - **'fa-circle-notch fa-spin'**: Processing/unconfirmed (spinner)
            - **'fa-exclamation-circle'**: Partial payment (warning)
            - **'fa-hourglass-half'**: Pending (hourglass)
            - **'fa-times-circle'**: Failed (X mark)
            - **'fa-clock'**: Expired (clock)

        Examples
        --------
        >>> payment = env['monero.payment'].browse(123)
        >>> icon = payment._get_status_icon()
        >>> # Use in template: <i class="fa {{ icon }}"></i>
        """
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
        """Get human-readable status message for current payment state.

        Returns a localized, user-friendly description of the current
        payment status with relevant details like amounts and confirmations.

        Returns
        -------
        str
            Localized status message with format:
            
            - **pending**: "Waiting for payment..."
            - **partial**: "Partial payment received (X/Y XMR)"  
            - **paid_unconfirmed**: "Payment received (confirming... N/M confirmations)"
            - **confirmed**: "Payment confirmed!"
            - **expired**: "Payment expired"
            - **failed**: "Payment failed: {error_message}"
            - **overpaid**: "Payment received (overpaid)"

        Notes
        -----
        The confirmation progress shows current confirmations vs required
        threshold from the payment provider configuration.

        Examples
        --------
        >>> payment = env['monero.payment'].browse(123)
        >>> message = payment._get_status_message()
        >>> print(message)  # "Payment received (confirming... 1/2 confirmations)"
        """
        self.ensure_one()
        provider = self.env['payment.provider']._get_monero_provider()
        # Issue 39: apply _() to the template string BEFORE substitution so Odoo
        # can extract the translatable string at build time.
        state = self.state
        if state == 'pending':
            return _("Waiting for payment...")
        elif state == 'partial':
            return _("Partial payment received (%.12f/%.12f XMR)") % (
                self.amount_received, self.amount)
        elif state == 'paid_unconfirmed':
            # Issue 4: provider may be empty recordset if misconfigured — guard with fallback
            threshold = provider.confirmation_threshold if provider else 10
            return _("Payment received (confirming... %d/%d confirmations)") % (
                self.confirmations, threshold)
        elif state == 'confirmed':
            return _("Payment confirmed!")
        elif state == 'expired':
            return _("Payment expired")
        elif state == 'failed':
            return _("Payment failed: %s") % (self.error_message or _("Unknown error"))
        elif state == 'overpaid':
            return _("Payment received (overpaid)")
        return _("Pending")

    def get_expiry_time(self):
        """Get formatted remaining time until payment expiration.

        Calculates and formats the time remaining until this payment expires.
        Useful for displaying countdown timers in user interfaces.

        Returns
        -------
        str
            Formatted time remaining in "Xh Ym" format, or "Expired" if past expiration

        Examples
        --------
        >>> payment = env['monero.payment'].browse(123)
        >>> time_left = payment.get_expiry_time()
        >>> print(time_left)  # "2h 30m" or "Expired"

        Usage in templates:

        >>> # Show countdown in payment page
        >>> <span class="countdown">{{ payment.get_expiry_time() }}</span>
        """
        self.ensure_one()
        if not self.expiration:
            return ""
            
        delta = self.expiration - fields.Datetime.now()
        if delta.total_seconds() <= 0:
            return _("Expired")

        total_secs = int(delta.total_seconds())
        hours, remainder = divmod(total_secs, 3600)
        minutes = remainder // 60
        return f"{hours}h {minutes}m"
