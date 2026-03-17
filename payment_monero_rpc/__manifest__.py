{
    "name": "payment_monero_rpc",
    "summary": "This module enables private and secure Monero (XMR) payments across your Odoo website and point of sale (POS) systems. It features full RPC integration for seamless interaction with a Monero daemon, real-time transaction tracking, and automated processing of payments. Ideal for merchants seeking privacy-focused crypto payments, the app supports both online and in-store transactions with customizable templates, frontend components, and POS interface enhancements.",
    "author": "Monero Integrations",
    "website": "https://monerointegrations.com/",
    "category": "Payment Providers",
    #"version": "19.0.0.0.3", for v19
    "version": "18.0.0.0.3",
    "license": "LGPL-3",
    "depends": [
        "account",
        "website_sale",
        "website_payment",
        "website",
        "payment",
        "base_setup",
        "web",
        "point_of_sale",
        "pos_online_payment"
    ],
    "external_dependencies": {
        "python": [
            "monero",
            "requests",
            "qrcode"
        ],
        "npm": []
    },
    "data": [
        #"security/monero_groups.xml", to make work on v19 uncomment this line and comment out the security.xml line
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/mail_templates.xml",
        "data/monero_payment_data.xml",
        "views/monero_daemon_views.xml",
        "views/monero_payment_views.xml",
        "views/monero_payment_templates.xml",
        "views/monero_payment_template_email.xml",
        "views/monero_payment_template_invoice.xml",
        "views/monero_payment_template_proof.xml",
        "views/monero_payment_kanban.xml",
        "views/pos_payment_views.xml",
        "views/menus.xml",
        "data/monero_cron.xml"
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_monero_rpc/static/src/css/monero.css",
            "payment_monero_rpc/static/src/css/monero_pos.css",
            "payment_monero_rpc/static/src/css/payment_page.css",                        
            "payment_monero_rpc/static/src/js/payment_form_monero.js",
            "payment_monero_rpc/static/src/js/payment_monero_checkout.js"
        ],
        "web.assets_backend": [
            "payment_monero_rpc/static/src/xml/monero_payment_template_page.xml"
        ],
        "point_of_sale._assets_pos": [
            "payment_monero_rpc/static/src/app/online_payment_popup_monero.js",
            "payment_monero_rpc/static/src/app/payment_screen_monero.js",
            "payment_monero_rpc/static/src/app/online_payment_popup_monero.xml"
        ]
    },
    "demo": [
        "demo/demo.xml"
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    #comment out post_init_hook entry below to make work on v19
    "post_init_hook": "post_init_setup",
    "uninstall_hook": "uninstall_hook"
}
