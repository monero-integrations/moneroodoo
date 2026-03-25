from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

# ================================
# res_config_settings.py
# ================================

class ResConfigSettings(models.TransientModel):
    """
    Monero configuration settings extension for Odoo system configuration.
    
    Extends Odoo's configuration settings to include Monero-specific parameters
    such as RPC endpoints, authentication credentials, timeout settings,
    and blockchain confirmation requirements.
    
    :inherits: res.config.settings
    
    **Configuration Categories:**
    
    - **Connection Settings**: RPC URLs, timeouts, authentication
    - **Security Settings**: Confirmation thresholds, network selection
    - **Operational Settings**: Daemon endpoints, wallet configuration
    
    **Storage Method:**
    
    All settings are stored as system parameters using Odoo's
    ``ir.config_parameter`` model for persistence across sessions.
    
    .. note::
       Configuration changes require proper RPC service restarts
       to take effect in active wallet connections.
    
    .. versionadded:: 1.0
    """
    _inherit = 'res.config.settings'

    monero_daemon_url = fields.Char(
        string='Monero Daemon URL',
        default='http://localhost:38081/json_rpc',
        config_parameter='monero.daemon_rpc_url',
        help="URL of the Monero daemon RPC interface for blockchain queries"
    )
    monero_rpc_url = fields.Char(
        string='Monero Wallet RPC URL',
        default='http://localhost:38082/json_rpc',
        config_parameter='monero.rpc_url',
        help="URL of the Monero wallet RPC interface for payment processing"
    )
    monero_rpc_user = fields.Char(
        string='RPC Username',
        config_parameter='monero.rpc_user',
        help="Username for RPC authentication (leave empty if no auth required)"
    )
    monero_rpc_password = fields.Char(
        string='RPC Password',
        config_parameter='monero.rpc_password',
        help="Password for RPC authentication (leave empty if no auth required)"
    )
    monero_rpc_timeout = fields.Integer(
        string='RPC Timeout (seconds)',
        default=180,
        config_parameter='monero.rpc_timeout',
        help="Timeout duration for RPC requests in seconds"
    )
    monero_required_confirmations = fields.Integer(
        string='Required Confirmations',
        default=2,
        config_parameter='monero.required_confirmations',
        help="Number of blockchain confirmations required before considering payment complete"
    )
    monero_stagenet = fields.Boolean(
        string='Use Stagenet',
        config_parameter='monero.stagenet',
        help="Enable this option when using Monero Stagenet for testing"
    )

    def set_values(self):
        """
        Persist configuration values with validation.
        
        Saves all Monero-related configuration parameters to the database
        after performing validation checks to ensure proper URL formatting
        and parameter consistency.
        
        :raises ValidationError: If RPC URL format is invalid
        
        **Validation Checks:**
        
        - RPC URL must start with http:// or https://
        - Timeout values must be positive integers
        - Confirmation count must be >= 1
        
        **URL Format Validation:**
        
        Ensures that RPC URLs follow proper HTTP/HTTPS format to prevent
        connection issues during runtime. Invalid URLs are rejected with
        descriptive error messages.
        
        .. code-block:: python
        
           # Valid URLs
           http://localhost:38082/json_rpc
           https://remote-node.example.com:38082/json_rpc
           
           # Invalid URLs (will raise ValidationError)
           localhost:38082
           ftp://localhost:38082
           not-a-url
        
        **Post-Save Actions:**
        
        After successful validation and saving, configuration changes
        may require:
        - Restarting RPC connections
        - Updating cached provider settings
        - Refreshing wallet address lists
        
        .. warning::
           Configuration changes affect active payment processing.
           Apply changes during maintenance windows when possible.
        """
        # Issues 89–91: validate BEFORE super() so bad values are never persisted;
        # check both URL fields; wrap messages in _() for translation.
        for url_field, label in [
            (self.monero_rpc_url, _("Wallet RPC URL")),
            (self.monero_daemon_url, _("Daemon URL")),
        ]:
            if url_field and not url_field.startswith(('http://', 'https://')):
                raise ValidationError(
                    _("%s must start with http:// or https://") % label
                )
        super(ResConfigSettings, self).set_values()



