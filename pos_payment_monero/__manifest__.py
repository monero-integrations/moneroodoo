{
    "name": "Monero POS Payments",
    "summary": "Allows you to accept Monero Payments within Odoo Point Of Sale",
    "author": "Monero Integrations",
    "website": "https://monerointegrations.com/",
    "category": "Point of Sale",
    "version": "14.0.1.0.0",
    "depends": [
        "account",
        "queue_job",
        "point_of_sale",
        "base_monero",
    ],
    "external_dependencies": {"python": ["monero"]},
    # always loaded
    "data": [
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
