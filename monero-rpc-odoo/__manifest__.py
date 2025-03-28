{
    "name": "monero-rpc-odoo",
    "summary": "Allows you to accept Monero Payments",
    "author": "Monero Integrations",
    "website": "https://monerointegrations.com/",
    # Categories can be used to filter modules in modules listing
    # for the full list
    "category": "Accounting",
    "version": "18.0.0.0.1",
    "icon": "/monero_rpc_odoo/static/description/icon.png",
    # any module necessary for this one to work correctly
    "depends": [
        "website_sale",
        "website_payment",
        "website",
        "payment",
        "base_setup",
        "web",
        "queue_job",
    ],
    "external_dependencies": {"python": ["monero"]},
    # always loaded
    "data": [
        "views/monero_payment_provider_form.xml",
        "views/monero_payment_confirmation.xml",
        "data/currency.xml",
        "data/monero_xmr_payment_provider.xml",
        "data/payment_icon_data.xml",
        "data/payment_provider_data.xml",
        "data/queue.xml",
    ],
    # only loaded in demonstration mode
    # TODO add demo data
    "demo": [
        "demo/demo.xml",
    ],
    "installable": True,
    "application": True,
    "classifiers": ["License :: OSI Approved :: MIT License"],
}
