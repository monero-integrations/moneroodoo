Base Monero
=========================


[![Build Status](https://api.travis-ci.com/t-900-a/moneroodoo.svg?branch=main)](https://travis-ci.com/t-900-a/moneroodoo)
[![codecov](https://codecov.io/gh/t-900-a/moneroodoo/branch/main/graph/badge.svg?token=10S5GGNRHH)](https://codecov.io/gh/t-900-a/moneroodoo)

This module defines the Monero Currency.
It acts as a base for the other integration modules.
It sets the decimal precision to 12 digits. Depends on the oca module account_cryptocurrency to integrate monero in the accounting of odoo.

Configuration
=============


* Monero - This quickstart guide can guide you through the configuration of Monero specific
components. https://monero-python.readthedocs.io/en/latest/quickstart.html
  * monerod
    * https://www.getmonero.org/resources/moneropedia/daemon.html
    * Download: https://www.getmonero.org/downloads/#cli
  *   monero-wallet-rpc
        * Use a view-key on the server
        * https://www.getmonero.org/resources/developer-guides/wallet-rpc.html
        * Download: https://www.getmonero.org/downloads/#cli
* Odoo - Add-ons are installed by adding the specific module folder to the add-ons
  directory (restart
  required)
    * account_cryptocurrency
        * https://github.com/OCA/currency/
    * monero-rpc-odoo
        * https://github.com/monero-integrations/moneroodoo
        * The Monero payment acquirer is configured similar to other payment acquirers
            * https://www.odoo.com/documentation/user/14.0/general/payment_acquirers/payment_acquirers.html#configuration
    * Currency rate
      * You can enter the currency rate manually for Monero.
      * https://www.odoo.com/documentation/user/14.0/accounting/others/multicurrencies/how_it_works.html
      * Or use any of the currency rate update apps of odoo. (See Helping modules)
    * Pricelist
        * A pricelist should be created specifically for Monero
        * https://www.odoo.com/documentation/user/14.0/website/publish/multi_website.html#pricelists



Usage
=====

* Go to accounting/Configuration/Currencies. The Monero currency is added to the list and can be activated/deactivated.
* On the accounting Dashboard a new journal is created for the Monero Currency.
  
Helping modules
=====
* Automatic update the currency rates between fiat and crypto
    * currency_rate_update_cmc
        * https://github.com/OCA/currency/
* Inverse method for converting currencies
    * currency_rate_inverted
        * https://github.com/OCA/currency/


Bug Tracker
===========

Bugs are tracked on [GitHub Issues](https://github.com/monero-integrations/moneroodoo/issues).
In case of trouble, please check there if your issue has already been reported.
If you spotted it first, help us smashing it by providing a detailed and welcomed
[feedback](https://github.com/monero-integrations/moneroodoo/issues/new?body=module:%20monero-rpc-odoo%0Aversion:%14.0%0A%0A**Steps%20to%20reproduce**%0A-%20...%0A%0A**Current%20behavior**%0A%0A**Expected%20behavior**)?

Credits
=======

Contributors

* T-900 <https://github.com/t-900-a>
* bosd <https://github.com/bosd>

Maintainers

This module is maintained by Monero-Integrations.
![Monero-Integrations](/monero-rpc-odoo/static/src/img/monero-integrations.png)


This module is part of the [monero-integrations/moneroodoo](https://github.com/monero-integrations/moneroodoo) project on GitHub.

You are welcome to contribute. To learn how please visit the [Monero Taiga](https://taiga.getmonero.org/project/t-900-monero-x-odoo-integrations/).
