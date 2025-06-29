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

### Automated Payment Verification

The module implements Odoo cron jobs to:

- Periodically check for incoming transactions
- Verify transaction confirmations
- Update payment statuses accordingly
- Reconcile completed payments with orders

This automation ensures payment integrity and reduces manual verification requirements.

## Installation Requirements

- Odoo 18
- Access to a Monero wallet RPC instance
- Proper network configuration for RPC communication


## Configuration

After installation, the module can be configured through the Odoo Payment Provider settings:

### Payment Provider Implementation

The module now implements the `payment.provider` model instead of the deprecated `payment.acquirer` model that was used in versions prior to v15. This change follows Odoo's payment framework evolution and ensures proper integration with the current payment flow system.

### Secondary Address System

The module has moved away from using the long `payment_ids` (which are no longer supported) to using secondary Monero addresses for payment tracking. This architectural change provides better isolation between transactions and improves the reliability of payment matching.
1. Enable the Monero payment provider
2. Configure Monero RPC connection details
3. Set confirmation thresholds and verification intervals
4. Test the connection to ensure proper communication

## Package reorganization

The 2 modules monero-rpc-odoo and monero-rpc-odoo-pos have been merged into one and following the naming convention for payment modules renamed to payment_monero_rpc.

## Upgrading from Previous Versions

Due to significant changes in both Odoo's payment framework and this module's architecture, a clean installation is recommended when upgrading from versions prior to Odoo 18. Data migration scripts are included but should be tested in a staging environment before use in production.

