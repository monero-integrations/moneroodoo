{
    "name": "monero-rpc-odoo-pos",
    "summary": "Allows you to accept Monero Payments within Odoo Point Of Sale",
    "author": "Monero Integrations",
    "website": "https://monerointegrations.com/",
    # Categories can be used to filter modules in modules listing
    # for the full list
    "category": "Accounting",
    "version": "14.0.0.0.1",
    # any module necessary for this one to work correctly
    "depends": [
        "account",
        "base_setup",
        "web",
        "queue_job",
        "point_of_sale",
    ],
    "external_dependencies": {"python": ["monero"]},
    # always loaded
    "data": [
        # "data/currency.xml", # not including as xmr may already be there
        "data/monero_xmr_payment_method.xml",
        "data/queue.xml",
        "views/pos_payment_method_form.xml",
        "views/pos_payment_method_views.xml",
        "views/pos_payment_views.xml",
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
