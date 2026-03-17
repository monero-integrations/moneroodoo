from odoo import models, fields, api

# ================================
# monero_transaction.py
# ================================

class MoneroTransaction(models.Model):
    """
    Monero blockchain transaction record model.
    
    This model represents individual blockchain transactions related to Monero
    payments, storing transaction details, confirmation status, and metadata
    associated with incoming or outgoing transfers.
    
    :param _name: Model identifier ('monero.transaction')
    :type _name: str
    :param _description: Human-readable model description
    :type _description: str
    :param _order: Default record ordering (newest first)
    :type _order: str
    
    **Transaction Types:**
    
    - ``in``: Incoming payment received
    - ``out``: Outgoing payment sent
    - ``pending``: Transaction in mempool
    - ``failed``: Transaction failed or rejected
    
    **Key Features:**
    
    - Automatic confirmation counting based on block height
    - Transaction verification status tracking
    - Comprehensive transaction metadata storage
    - Integration with Monero payment records
    
    .. note::
       Transactions are automatically created when payments are detected
       and should not typically be created manually.
    
    .. versionadded:: 1.0
    """
    _name = 'monero.transaction'
    _description = 'Monero Transaction'
    _order = 'create_date desc'  # timestamp is optional/nullable; id desc is always stable

    _sql_constraints = [
        ('txid_unique', 'UNIQUE(txid)', 'Transaction hash must be unique!'),
    ]

    payment_id = fields.Many2one(
        'monero.payment',
        string="Payment",
        required=True,
        ondelete='cascade',
        help="Reference to the associated Monero payment record."
    )
    txid = fields.Char(
        string="Transaction Hash",
        required=True,
        index=True,
        help="Unique identifier of the Monero transaction."
    )
    amount = fields.Float(
        string="Amount",
        digits=(16, 12),
        required=True,
        help="Amount of XMR transferred in the transaction."
    )
    fee = fields.Float(
        string="Fee",
        digits=(16, 12),
        help="Transaction fee in XMR."
    )
    block_height = fields.Integer(
        string="Block Height",
        index=True,
        help="Height of the block that includes this transaction."
    )
    unlock_time = fields.Integer(
        string="Unlock Time",
        help="Time or block height when the transaction becomes spendable."
    )
    confirmations = fields.Integer(
        string="Confirmations",
        compute='_compute_confirmations',
        store=False,  # Issue 9: never store — block_height never changes after set,
                      # so a stored value becomes stale immediately. Compute live from
                      # the daemon cache (updated by the daemon cron) on every read.
        help="Number of confirmations the transaction has received."
    )
    timestamp = fields.Datetime(
        string="Timestamp",
        required=False,
        help="Date and time the transaction was created. Optional — may be absent for mempool transactions."
    )
    is_confirmed = fields.Boolean(
        string="Confirmed",
        compute='_compute_is_confirmed',
        store=False,  # Issue 1: confirmations is store=False; Odoo cannot trigger a
                      # stored recompute from a non-stored dependency. Compute live instead.
        help="Whether the transaction is confirmed based on threshold."
    )
    payment_type = fields.Selection(
        [
            ('in', 'Incoming'),
            ('out', 'Outgoing'),
            ('pending', 'Pending'),
            ('failed', 'Failed')
        ],
        string="Type",
        help="The type/status of the Monero transaction."
    )

    account_index = fields.Integer(string="Account Index", help="Index of the account involved in the transaction.")
    subaddr_index = fields.Integer(string="Subaddress Index", help="Index of the subaddress used.")
    local_address = fields.Char(string="Local Address", help="Address that received or sent the transaction.")
    note = fields.Char(string="Note", help="Optional note about the transaction.")
    tx_key = fields.Char(string="Transaction Key", help="Optional transaction key (if available).")
    double_spend_seen = fields.Boolean(string="Double Spend Seen", help="Whether double spending was detected.")
    in_pool = fields.Boolean(string="In Mempool", help="Indicates whether the transaction is still in mempool.")
    extra = fields.Text(string="Extra", help="Extra data embedded in the transaction.")
    stealth_address = fields.Char(string="Stealth Address", help="Stealth address used in the transaction.")

    @api.depends('block_height')
    def _compute_confirmations(self):
        """
        Compute the number of confirmations for each transaction.
        
        Calculates confirmations by comparing the current blockchain height
        with the transaction's block height. Confirmations represent the
        number of blocks that have been mined after the transaction block.
        
        **Confirmation Calculation:**
        
        ``confirmations = max(0, current_height - transaction_block_height)``
        
        **States:**
        
        - ``0 confirmations``: Transaction not yet in a block (mempool)
        - ``1+ confirmations``: Transaction included in blockchain
        - Higher confirmations indicate greater security
        
        .. code-block:: python
        
           # Transaction in block 100, current height 105
           # confirmations = 105 - 100 = 5
        
        .. note::
           Sets confirmations to 0 if:
           - Transaction has no block height (still in mempool)
           - Current blockchain height unavailable
           - Calculated value would be negative
        """
        # Fetch block height once outside loop to avoid N sequential RPC calls
        # Issue 60/61: read from the daemon cache — no live RPC on UI load.
        # The daemon cron updates monero.daemon regularly; use that record.
        daemon = self.env['monero.daemon'].search([], limit=1, order='last_checked desc')
        current_height = daemon.current_height if daemon and daemon.current_height else 0
        for tx in self:
            if not tx.block_height or not current_height:
                tx.confirmations = 0
                continue
            tx.confirmations = max(0, current_height - tx.block_height)

    @api.depends('confirmations')
    def _compute_is_confirmed(self):
        """
        Determine whether the transaction has sufficient confirmations.
        
        Compares the transaction's confirmation count against the configured
        threshold from the Monero payment provider to determine if the
        transaction should be considered fully confirmed.
        
        **Confirmation Logic:**
        
        ``is_confirmed = confirmations >= provider_threshold``
        
        **Provider Threshold:**
        
        The confirmation threshold is configured in the payment provider
        settings and typically ranges from 1-10 confirmations depending
        on security requirements.
        
        **Use Cases:**
        
        - Payment processing automation
        - Security verification
        - Transaction status display
        - Automated order fulfillment triggers
        
        .. seealso::
           :attr:`payment.provider.confirmation_threshold` for threshold configuration
        """
        provider = self.env['payment.provider']._get_monero_provider()
        # Issue 62: default to 10 (safe high number) rather than 2 if provider is
        # misconfigured, to avoid silently under-confirming payments.
        threshold = (provider.confirmation_threshold if provider else 0) or 10
        for tx in self:
            tx.is_confirmed = tx.confirmations >= threshold

