import base64
from odoo.modules.module import get_module_resource
from odoo import SUPERUSER_ID

def load_monero_logo():
    logo_path = get_module_resource('payment_monero_rpc', 'static/src/img', 'logo.png')
    with open(logo_path, 'rb') as logo_file:
        return base64.b64encode(logo_file.read())

def associate_monero_with_pos_configs(cr, registry):
    from odoo.api import Environment
    env = Environment(cr, SUPERUSER_ID, {})
    logo_base64 = load_monero_logo()

    PaymentMethod = env['pos.payment.method']
    monero_method = PaymentMethod.search([('name', '=', 'Monero RPC')], limit=1)
    if not monero_method:
        monero_method = PaymentMethod.create({
            'name': 'Monero RPC',
            'is_cash_count': False,
            'use_payment_terminal': False,
            'image': logo_base64,
        })
    elif not monero_method.image:
        monero_method.image = logo_base64

    PaymentProvider = env['payment.provider']
    monero_provider = PaymentProvider.search([('code', '=', 'monero')], limit=1)
    if monero_provider and not monero_provider.image_128:
        monero_provider.image_128 = logo_base64

    target_pos_names = ['Furniture Shop', 'Bakery Shop', 'Clothes Shop']
    PosConfig = env['pos.config']
    for name in target_pos_names:
        pos_config = PosConfig.search([('name', '=', name)], limit=1)
        if pos_config and monero_method not in pos_config.payment_method_ids:
            pos_config.payment_method_ids += monero_method

