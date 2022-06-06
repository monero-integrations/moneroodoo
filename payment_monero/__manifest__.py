{
    "name": "Monero Payments",
    "summary": "Allows you to accept Monero Payments",
    "author": "Monero Integrations",
    "website": "https://monerointegrations.com/",
    # Categories can be used to filter modules in modules listing
    # for the full list
    "category": "Accounting",
    "version": "14.0.1.0.0",
    "development_status": "Alpha",
    # any module necessary for this one to work correctly
    "depends": [
        "website_sale",
        "website_payment",
        "website",
        "payment_transfer",
        "payment",
        "web",
        "queue_job",
        "base_monero",
    ],
    "external_dependencies": {"python": ["monero"]},
    # always loaded
    "data": [
        "views/monero_acquirer_form.xml",
        "views/monero_payment_confirmation.xml",
        "data/monero_xmr_payment_acquirer.xml",
        "data/payment_icon_data.xml",
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
