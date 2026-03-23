{
    "name": "monero-rpc-odoo",
    "summary": "Allows you to accept Monero Payments",
    "author": "Monero Integrations",
    "website": "https://monerointegrations.com/",
    # Categories can be used to filter modules in modules listing
    # for the full list
    "category": "Accounting",
    "version": "19.0.1",
    # any module necessary for this one to work correctly
    "depends": [
        "website_sale",
        "website_payment",
        "website",
        "payment",
        "base_setup",
        "web",
    ],
    "external_dependencies": {"python": ["monero"]},
    # always loaded
    "data": [
        "views/monero_redirect_form.xml",
        "views/monero_acquirer_form.xml",
        "views/monero_payment_confirmation.xml",
        "data/currency.xml",
        "data/monero_xmr_payment_acquirer.xml",
        "data/xmr_rate_cron.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "monero_rpc_odoo/static/src/js/jquery.qrcode.min.js",
            "monero_rpc_odoo/static/src/js/monero_payment.js",
        ],
    },
    # only loaded in demonstration mode
    # TODO add demo data
    "demo": [
        "demo/demo.xml",
    ],
    "installable": True,
    "application": True,
    "classifiers": ["License :: OSI Approved :: MIT License"],
}
