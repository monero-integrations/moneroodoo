from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    monero_rpc_url = fields.Char(
        string='Monero RPC URL',
        default='http://localhost:38082/json_rpc',
        config_parameter='monero.rpc_url',
        help="URL of the Monero wallet RPC interface"
    )
    monero_rpc_user = fields.Char(
        string='RPC Username',
        config_parameter='monero.rpc_user',
        help="Username for RPC authentication"
    )
    monero_rpc_password = fields.Char(
        string='RPC Password',
        config_parameter='monero.rpc_password',
        help="Password for RPC authentication"
    )
    monero_rpc_timeout = fields.Integer(
        string='RPC Timeout (seconds)',
        default=180,
        config_parameter='monero.rpc_timeout',
        help="Timeout for RPC requests in seconds"
    )
    monero_required_confirmations = fields.Integer(
        string='Required Confirmations',
        default=2,
        config_parameter='monero.required_confirmations',
        help="Number of confirmations required before considering payment complete"
    )
    monero_testnet = fields.Boolean(
        string='Use Stagenet',
        config_parameter='monero.stagenet',
        help="Enable this if using Monero Stagenet"
    )

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        if self.monero_rpc_url and not self.monero_rpc_url.startswith(('http://', 'https://')):
            raise ValidationError("RPC URL must start with http:// or https://")
