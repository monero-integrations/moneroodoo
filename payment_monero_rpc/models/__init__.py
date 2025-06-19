from . import payment_provider, monero_payment, monero_transactions, monero_daemons, res_config_settings, pos_payment


import hashlib
import os

def initialize_proof_system():
    if not os.getenv('ODOO_MONERO_PROOF_KEY'):
        key = secrets.token_hex(32)
        os.environ['ODOO_MONERO_PROOF_KEY'] = key
        config = self.env['ir.config_parameter'].sudo()
        config.set_param('monero.payment_proof_key', key)
