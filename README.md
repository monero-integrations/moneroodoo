[![Build Status](https://api.travis-ci.com/t-900-a/moneroodoo.svg?branch=main)](https://travis-ci.com/t-900-a/moneroodoo)
[![codecov](https://codecov.io/gh/t-900-a/moneroodoo/branch/main/graph/badge.svg?token=10S5GGNRHH)](https://codecov.io/gh/t-900-a/moneroodoo)
# Monero addons for Odoo

Allows you to accept Monero as Payment within your Odoo Ecommerce shop

- Full compatibility with Odoo 18
- RPC communication with Monero daemon/wallet using Python Monero
- Automated payment verification through scheduled jobs
- Support for multiple wallet addresses as long `payment_ids` (which were used in previous version) are no longer supported
- Seamless integration with Odoo's payment flow
- Periodically check for incoming transactions
- Verify transaction confirmations
- Update payment statuses accordingly
- Reconcile completed payments with orders

![Monero](https://raw.githubusercontent.com/t-900-a/moneroodoo/dev/monero-rpc-odoo/static/src/img/logo.png)


Available addons
----------------
|  addon | version  | summary  |
|---|---|---|
|  [monero-rpc-odoo](monero-rpc-odoo/) |  18.0.0.0.1 |  Accept Monero Payment via a Wallet RPC |
