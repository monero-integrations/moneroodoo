# ================================
# hooks.py
# ================================
import logging
import os
import base64
import secrets

from odoo import SUPERUSER_ID
from odoo.modules import module

_logger = logging.getLogger(__name__)

_logo_cache = None  # Module-level cache to avoid repeated file reads


def get_monero_logo_path():
    """Return the absolute filesystem path to the Monero logo."""
    return os.path.join(
        module.get_module_path('payment_monero_rpc'),
        'static', 'src', 'img', 'logo_chain.png'
    )


def _load_monero_logo():
    """Return the base64-encoded Monero logo from module resources."""
    global _logo_cache
    if _logo_cache:
        return _logo_cache
    logo_path = get_monero_logo_path()
    if not os.path.exists(logo_path):
        _logger.warning("Monero logo not found at %s", logo_path)
        return None
    with open(logo_path, 'rb') as logo_file:
        _logo_cache = base64.b64encode(logo_file.read())
    return _logo_cache


def _initialize_proof_system(env):
    """Generate and store a Monero payment proof key if not already set.

    Stores the key in ir.config_parameter, which is accessible from all
    worker processes. Using os.environ would only set it in the current
    worker, making the key unavailable in others.

    .. warning::
       If the module is fully uninstalled and reinstalled, a NEW key will be
       generated, making all previously generated payment proofs permanently
       unverifiable. Back up the key from ir.config_parameter before reinstalling.
    """
    config = env['ir.config_parameter'].sudo()
    key = config.get_param('monero.payment_proof_key')
    if not key:
        key = secrets.token_hex(32)
        config.set_param('monero.payment_proof_key', key)
        _logger.info("Monero payment proof key generated and stored in ir.config_parameter")
    else:
        _logger.info("Monero payment proof key already configured")


def _create_security_groups(env):
    """Security groups are defined authoritatively in security/security.xml.

    This function is intentionally a no-op — XML data files are the correct
    place to create groups. Duplicating group creation here causes conflicts
    between the hook and the XML loader on reinstall.
    """
    _logger.debug("Security groups managed by security/security.xml — skipping hook creation")


def post_init_setup(cr, registry):
    """Main post-init hook for the Monero payment module.

    Runs once after module installation to bootstrap core systems.
    """
    from odoo.api import Environment
    env = Environment(cr, SUPERUSER_ID, {})

    _logger.info("Initializing Monero RPC module")
    _initialize_proof_system(env)
    _create_security_groups(env)
    _logger.info("Monero RPC module initialization completed successfully")


def uninstall_hook(cr, registry):
    """Cleanup hook that runs when the module is uninstalled.

    Note: The payment proof key is intentionally NOT deleted here.
    Deleting it would make all previously generated payment proofs
    permanently unverifiable. Admins can delete it manually if desired.

    Note: The ODOO_MONERO_PROOF_KEY environment variable is NOT used anywhere
    in this module — the key is stored exclusively in ir.config_parameter.
    No env-var cleanup is performed.
    """
    from odoo.api import Environment
    env = Environment(cr, SUPERUSER_ID, {})  # noqa: kept for potential future cleanup

    _logger.info(
        "Monero RPC module uninstalled. "
        "Payment proof key preserved in ir.config_parameter — delete manually if no longer needed."
    )
