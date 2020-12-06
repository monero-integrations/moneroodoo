# -*- coding: utf-8 -*-
{
    'name': "moneroodoo",

    'summary': """
        Allows you to accept Monero as Payment within your Odoo Ecommerce shop""",

    'description': """
        Payment Acquierer built for Odoo 14; The private Monero cryptocurrency can be accepted.
        Transactions can be configured to be almost instant and are low-cost
    """,

    'author': "Monero Integrations",
    'website': "https://monerointegrations.com/",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/odoo/addons/base/module/module_data.xml
    # for the full list
    'category': 'Accounting',
    'version': '0.2',

    # any module necessary for this one to work correctly
    'depends': ['website_sale',
                'website_payment',
                'website',
                'payment_transfer',
                'payment',
                'base_setup',
                'web',
                ],

    # always loaded
    'data': [
        'views/scheduler.xml',
        'views/monero_acquirer_form.xml',
        'views/monero_payment_confirmation.xml',
        'data/currency.xml',
        'data/monero_xmr_payment_acquirer.xml',
    ],
    # only loaded in demonstration mode
    # TODO add demo data
    'demo': [
        'demo/demo.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'MIT License',
}