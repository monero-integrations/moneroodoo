from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import monero
from monero.backends.jsonrpc import JSONRPCDaemon
from monero.exceptions import NoDaemonConnection, DaemonIsBusy

_logger = logging.getLogger(__name__)

class MoneroDaemon(models.Model):
    _name = 'monero.daemon'
    _description = 'Monero Daemon Status'

    name = fields.Char(default='Monero Daemon')
    last_checked = fields.Datetime(readonly=True)
    state = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('syncing', 'Syncing')
    ], readonly=True)
    network = fields.Selection([
        ('mainnet', 'Mainnet'),
        ('testnet', 'Testnet'),
        ('stagenet', 'Stagenet')
    ], readonly=True)
    version = fields.Char(readonly=True)
    current_height = fields.Integer(readonly=True)
    target_height = fields.Integer(readonly=True)
    connections = fields.Integer(readonly=True)
    update_available = fields.Boolean(readonly=True)
    last_error = fields.Text(readonly=True)

    @api.model
    def get_current_height(self):
        daemon = self.search([], limit=1, order='id desc')
        return daemon.current_height if daemon else 0

    @api.model
    def _cron_check_daemon_status(self):
        """Regular daemon status check using monero-python"""
        _logger.info("==== CRON JOB STARTED ====")
        try:
            provider = self.env['payment.provider'].search([('code', '=', 'monero_rpc')], limit=1)
            if not provider:
                error_msg = "Monero RPC provider not found"
                _logger.error(error_msg)
                return False
            
            daemon = self.env['monero.daemon'].search([], limit=1, order='id desc')
            if not daemon:
                self.env['monero.daemon'].sudo().create({
                    'last_checked': fields.Datetime.now(),
                    'state': 'offline',
                    'network': 'stagenet',
                    'version': 'unknown',
                    'current_height': 0,
                    'target_height': 0,
                    'connections': 0,
                    'update_available': False,
                    'last_error': False
                })

            try:
                daemon_rpc = provider._get_daemon()

                info = daemon_rpc.info()
                
                vals = {
                    'last_checked': fields.Datetime.now(),
                    'state': 'online',
                    'network': provider.network_type,
                    'version': info.version,
                    'current_height': info.height,
                    'target_height': info.target_height,
                    'connections': info.incoming_connections_count + info.outgoing_connections_count,
                    'update_available': info.update_available,
                    'last_error': False
                }
                
                if vals['current_height'] < vals['target_height']:
                    vals['state'] = 'syncing'
                
                daemon = self.search([], limit=1, order='id desc')
                daemon.sudo().write(vals)
                _logger.info("Monero daemon record updated %s", vals)
                return True
                
            except NoDaemonConnection as e:
                _logger.error("Daemon connection failed: %s", str(e))
                self.update({
                    'last_checked': fields.Datetime.now(),
                    'state': 'offline',
                    'last_error': str(e)
                })
            except DaemonIsBusy as e:
                _logger.error("Daemon is busy: %s", str(e))
                self.update({
                    'last_checked': fields.Datetime.now(),
                    'state': 'offline',
                    'last_error': str(e)
                })
                
        except Exception as e:
            _logger.exception("Failed to check daemon status")
            raise UserError(_("Failed to check daemon status: %s") % str(e))
