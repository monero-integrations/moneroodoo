{
    "name": "Monero RPC",
    "summary": "A free and open source payment gateway to accept online Monero payments.",
    "author": "Monero Integrations",
    "website": "https://monerointegrations.com/",
    # Categories can be used to filter modules in modules listing
    # for the full list
    "category": "Accounting",
    "version": "15.0",
    "license": "AGPL-3.0",
    # any module necessary for this one to work correctly
    "depends": [
        "website_sale",
        "website_payment",
        "website",
        "payment_transfer",
        "payment",
        "base_setup",
        "web",
        "queue_job",
    ],
    "external_dependencies": {"python": ["monero"]},
    # always loaded
    "data": [
        "views/monero_acquirer_form.xml",
        "views/monero_payment_confirmation.xml",
        "data/currency.xml",
        "data/monero_payment_acquirer.xml",
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
} # type: ignore
