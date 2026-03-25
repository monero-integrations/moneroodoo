# ================================
# monero_daemon.py
# ================================

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
from monero.daemon import Daemon
from monero.backends.jsonrpc import JSONRPCDaemon
from monero.exceptions import NoDaemonConnection, DaemonIsBusy

_logger = logging.getLogger(__name__)

class MoneroDaemon(models.Model):
    """
    Monero Daemon Status monitoring and management model.
    
    This model tracks the current status of the Monero daemon node, including
    synchronization progress, version information, network statistics, and
    overall daemon health monitoring.
    
    :param _name: Model identifier ('monero.daemon')
    :type _name: str
    :param _description: Human-readable model description
    :type _description: str
    
    **Key Features:**
    
    - Real-time daemon status monitoring
    - Blockchain synchronization tracking
    - Network statistics collection
    - Automated health checks via cron jobs
    - Historical status record management
    
    .. note::
       This model is designed to work with a single daemon instance
       and maintains historical records for monitoring purposes.
    
    .. versionadded:: 1.0
    """
    _name = 'monero.daemon'
    _description = 'Monero Daemon Status'

    name = fields.Char(default='Monero Daemon')
    last_checked = fields.Datetime(readonly=True)
    state = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('syncing', 'Syncing')
    ], readonly=True, default='offline')
    network = fields.Selection([
        ('mainnet', 'Mainnet'),
        ('testnet', 'Testnet'),
        ('stagenet', 'Stagenet')
    ], readonly=True, default='stagenet')
    version = fields.Char(readonly=True, default='unknown')
    current_height = fields.Integer(readonly=True, default=0)
    target_height = fields.Integer(readonly=True, default=0)
    connections = fields.Integer(readonly=True, default=0)
    update_available = fields.Boolean(readonly=True, default=False)
    last_error = fields.Text(readonly=True)

    # Additional fields for detailed daemon info
    difficulty = fields.Char(readonly=True, help="Current network difficulty (stored as string due to large values)")
    cumulative_difficulty = fields.Char(readonly=True, help="Cumulative network difficulty (stored as string due to large values)")
    target = fields.Integer(readonly=True, default=0)
    top_block_hash = fields.Char(readonly=True)
    free_space = fields.Float(readonly=True, default=0.0, help="Free space in GB")
    uptime = fields.Integer(readonly=True, default=0, help="Uptime in seconds")
    database_size = fields.Float(readonly=True, default=0.0, help="Database size in MB")

    @api.model
    def get_current_height(self):
        """
        Get the current blockchain height from the most recent daemon record.
        
        Retrieves the blockchain height from the latest daemon status record,
        which is used for confirmation calculations and payment verification.
        
        :returns: The last recorded blockchain height, or 0 if no records exist
        :rtype: int
        
        **Usage Example:**
        
        .. code-block:: python
        
           current_height = self.env['monero.daemon'].get_current_height()
           if current_height > 0:
               # Process confirmations
               pass
        
        .. note::
           Returns 0 if no daemon records exist or if an error occurs
        """
        try:
            daemon = self.search([], limit=1, order='last_checked desc')
            if not daemon or not daemon.current_height:
                return None  # distinguish "no daemon" from "height is 0"
            return daemon.current_height
        except Exception as e:
            _logger.error("Error getting current height: %s", str(e))
            return None

    @api.model
    def get_or_create_daemon_record(self):
        """
        Retrieve the latest daemon record, or create a new one if none exists.
        
        This method ensures there's always a daemon record available for status
        updates. If no records exist, it creates a new one with default values.
        
        :returns: The existing or newly created daemon record
        :rtype: monero.daemon
        
        **Default Values for New Records:**
        
        - ``state``: 'offline'
        - ``network``: 'stagenet'
        - ``version``: 'unknown'
        - All numeric fields: 0
        - ``last_error``: False
        
        .. versionadded:: 1.0
        """
        # Use SELECT FOR UPDATE to prevent race condition between concurrent workers
        self.env.cr.execute(
            "SELECT id FROM monero_daemon ORDER BY last_checked DESC LIMIT 1 FOR UPDATE"
        )
        row = self.env.cr.fetchone()
        if row:
            return self.browse(row[0])
        # Safe to create — lock is held
        provider = self.env['payment.provider'].search(
            [('code', '=', 'monero_rpc')], limit=1)
        # Default to stagenet if no provider — safer than mainnet for unconfigured installs
        network = provider.network_type if provider else 'stagenet'
        return self.create({
                'last_checked': fields.Datetime.now(),
                'state': 'offline',
                'network': network,
                'version': 'unknown',
                'current_height': 0,
                'target_height': 0,
                'connections': 0,
                'update_available': False,
                'last_error': False
            })

    @api.model
    def cleanup_old_records(self, keep_latest=5):
        """
        Maintain only the latest N daemon records to prevent database bloat.
        
        This method automatically removes old daemon status records, keeping
        only the most recent ones for historical reference.
        
        :param int keep_latest: Number of recent records to preserve
        
        **Cleanup Process:**
        
        1. Retrieves all records ordered by creation date (newest first)
        2. Identifies records beyond the keep limit
        3. Removes excess records using sudo privileges
        4. Logs the cleanup operation
        
        .. code-block:: python
        
           # Keep only the latest 10 records
           self.cleanup_old_records(keep_latest=10)
        
        .. warning::
           This operation permanently deletes old records. Ensure the
           keep_latest value meets your historical data requirements.
        """
        try:
            all_records = self.search([], order='last_checked desc')
            if len(all_records) > keep_latest:
                old_records = all_records[keep_latest:]
                old_records.unlink()
                _logger.info("Cleaned up %d old daemon records", len(old_records))
        except Exception as e:
            _logger.error("Error cleaning up old daemon records: %s", str(e))

    def _safe_getattr(self, obj, attr, default=None, convert_to_str=False):
        """
        Safely extract an attribute from a daemon info object.
        
        Provides safe attribute access with error handling and optional
        string conversion for large numeric values.
        
        :param object obj: Source object to extract attribute from
        :param str attr: Attribute name to retrieve
        :param any default: Default value if attribute doesn't exist
        :param bool convert_to_str: Whether to convert the value to string
        :returns: Attribute value or default
        :rtype: any
        
        **Use Cases:**
        
        - Extracting daemon info fields safely
        - Converting large numbers to strings
        - Handling missing attributes gracefully
        
        .. code-block:: python
        
           # Safe numeric extraction
           height = self._safe_getattr(info, 'height', 0)
           
           # Large number as string
           difficulty = self._safe_getattr(info, 'difficulty', '0', convert_to_str=True)
        """
        try:
            value = getattr(obj, attr, default)
            return str(value) if convert_to_str and value is not None else value
        except Exception as e:
            _logger.warning("Error getting attribute %s: %s", attr, str(e))
            return default

    def _convert_bytes_to_mb(self, bytes_value):
        """
        Convert bytes to megabytes with proper error handling.
        
        :param bytes_value: Value in bytes to convert
        :type bytes_value: int or float
        :returns: Value in megabytes, rounded to 2 decimal places
        :rtype: float
        
        .. note::
           Returns 0.0 for invalid or None input values
        """
        try:
            return round(bytes_value / (1024 * 1024), 2) if bytes_value else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _convert_bytes_to_gb(self, bytes_value):
        """
        Convert bytes to gigabytes with proper error handling.
        
        :param bytes_value: Value in bytes to convert
        :type bytes_value: int or float
        :returns: Value in gigabytes, rounded to 2 decimal places
        :rtype: float
        
        .. note::
           Returns 0.0 for invalid or None input values
        """
        try:
            return round(bytes_value / (1024 * 1024 * 1024), 2) if bytes_value else 0.0
        except (TypeError, ValueError):
            return 0.0

    @api.model
    def _cron_check_daemon_status(self):
        """
        Periodic scheduled task to check Monero daemon status and update records.
        
        This cron job connects to the Monero daemon, retrieves current status
        information, and updates the daemon record with the latest data.
        
        :returns: True if status check succeeded, False otherwise
        :rtype: bool
        
        **Status Check Process:**
        
        1. Locate or create daemon record
        2. Connect to Monero payment provider
        3. Retrieve daemon information via RPC
        4. Update record with current status
        5. Determine sync state based on height comparison
        6. Clean up old records
        
        **State Determination:**
        
        - ``online``: Daemon connected and fully synced
        - ``syncing``: Daemon connected but still synchronizing
        - ``offline``: Connection failed or daemon unavailable
        
        **Error Handling:**
        
        - ``NoDaemonConnection``: Sets state to offline
        - ``DaemonIsBusy``: Logs warning, sets state to offline
        - General exceptions: Logs error, updates record with error message
        
        .. code-block:: python
        
           # Manual status check
           success = self.env['monero.daemon']._cron_check_daemon_status()
           if success:
               print("Daemon status updated successfully")
        
        .. seealso::
           :meth:`get_daemon_status_summary` for retrieving status information
        """
        _logger.info("==== MONERO DAEMON STATUS CHECK STARTED ====")
        daemon = self.get_or_create_daemon_record()  # always defined before try
        try:
            provider = self.env['payment.provider'].search([('code', '=', 'monero_rpc')], limit=1)
            if not provider:
                error_msg = "Monero RPC provider not found"
                _logger.error(error_msg)
                daemon.sudo().write({
                    'last_checked': fields.Datetime.now(),
                    'state': 'offline',
                    'last_error': error_msg
                })
                return False

            daemon_rpc = provider._get_daemon()
            if not daemon_rpc:
                raise NoDaemonConnection("Failed to get daemon connection")
            info = daemon_rpc.info()
            if not info:
                raise NoDaemonConnection("Failed to get daemon info")

            vals = {
                'last_checked': fields.Datetime.now(),
                'state': 'online',
                'network': getattr(provider, 'network_type', 'stagenet'),
                'version': self._safe_getattr(info, 'version', 'unknown'),
                'current_height': self._safe_getattr(info, 'height', 0),
                'target_height': self._safe_getattr(info, 'target_height', 0),
                'connections': (
                    self._safe_getattr(info, 'incoming_connections_count', 0) +
                    self._safe_getattr(info, 'outgoing_connections_count', 0)
                ),
                'update_available': self._safe_getattr(info, 'update_available', False),
                'last_error': False,
                'difficulty': self._safe_getattr(info, 'difficulty', '0', convert_to_str=True),
                'cumulative_difficulty': self._safe_getattr(info, 'cumulative_difficulty', '0', convert_to_str=True),
                'target': self._safe_getattr(info, 'target', 0),
                'top_block_hash': self._safe_getattr(info, 'top_block_hash', ''),
                'free_space': self._convert_bytes_to_gb(self._safe_getattr(info, 'free_space', 0)),
                'uptime': self._safe_getattr(info, 'uptime', 0),
                'database_size': self._convert_bytes_to_mb(self._safe_getattr(info, 'database_size', 0)),
            }

            if vals['target_height'] > 0 and vals['current_height'] < vals['target_height']:
                vals['state'] = 'syncing'

            daemon.sudo().write(vals)
            _logger.info("Monero daemon status updated successfully - State: %s, Height: %s/%s",
                         vals['state'], vals['current_height'], vals['target_height'])

            self.cleanup_old_records()
            return True

        except NoDaemonConnection as e:
            msg = f"Daemon connection failed: {str(e)}"
            _logger.error(msg)
            daemon.sudo().write({
                'last_checked': fields.Datetime.now(),
                'state': 'offline',
                'last_error': msg
            })
            return False

        except DaemonIsBusy as e:
            msg = f"Daemon is busy: {str(e)}"
            _logger.warning(msg)
            daemon.sudo().write({
                'last_checked': fields.Datetime.now(),
                'state': 'offline',
                'last_error': msg
            })
            return False

        except Exception as e:
            msg = f"Unexpected error checking daemon status: {str(e)}"
            _logger.exception(msg)
            try:
                # daemon is always defined before the try block — reuse it
                daemon.sudo().write({
                    'last_checked': fields.Datetime.now(),
                    'state': 'offline',
                    'last_error': msg
                })
            except Exception as update_error:
                _logger.error("Failed to update daemon record after error: %s", str(update_error))
            return False

    @api.model
    def get_daemon_status_summary(self):
        """
        Get a comprehensive summary of the daemon status for UI display.
        
        Retrieves the latest daemon status information and formats it for
        use in user interfaces, dashboards, and status displays.
        
        :returns: Dictionary containing formatted status information
        :rtype: dict
        
        **Response Structure:**
        
        .. code-block:: python
        
           {
               'state': 'online|offline|syncing',
               'network': 'mainnet|testnet|stagenet',
               'version': 'daemon_version_string',
               'current_height': 12345,
               'target_height': 12346,
               'sync_percentage': 99.92,
               'connections': 8,
               'last_checked': datetime_object,
               'last_error': 'error_message_or_false',
               'uptime': 86400  # seconds
           }
        
        **Sync Percentage Calculation:**
        
        The sync percentage is calculated as:
        ``(current_height / target_height) * 100``
        
        Capped at 100% to handle edge cases where current exceeds target.
        
        **Default Response (No Records):**
        
        If no daemon records exist, returns a minimal error state:
        
        .. code-block:: python
        
           {
               'state': 'offline',
               'message': 'No daemon status available',
               'last_checked': False
           }
        
        .. seealso::
           :meth:`_cron_check_daemon_status` for updating daemon status
        """
        daemon = self.search([], limit=1, order='last_checked desc')
        if not daemon:
            return {
                'state': 'offline',
                'message': 'No daemon status available',
                'last_checked': False
            }

        sync_percentage = 0
        if daemon.target_height > 0 and daemon.current_height > 0:
            sync_percentage = min(100, (daemon.current_height / daemon.target_height) * 100)

        return {
            'state': daemon.state,
            'network': daemon.network,
            'version': daemon.version,
            'current_height': daemon.current_height,
            'target_height': daemon.target_height,
            'sync_percentage': round(sync_percentage, 2),
            'connections': daemon.connections,
            'last_checked': daemon.last_checked,
            'last_error': daemon.last_error,
            'uptime': daemon.uptime,
        }

