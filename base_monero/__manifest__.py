{
    "name": "Monero Base",
    "summary": "Integrate Monero Currency in Odoo",
    "author": "Monero Integrations",
    "website": "https://monerointegrations.com/",
    # Categories can be used to filter modules in modules listing
    # for the full list
    "category": "Accounting",
    "version": "14.0.1.0.0",
    # any module necessary for this one to work correctly
    "depends": [
        "account_cryptocurrency",
    ],
    # "external_dependencies": {"python": ["monero"]},
    # always loaded
    "data": [
        "data/res_currency_data.xml",
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
