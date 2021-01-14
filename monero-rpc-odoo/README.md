=========================
Monero Odoo
=========================


[![Build Status](https://travis-ci.com/t-900-a/moneroodoo.svg?branch=master)](https://travis-ci.com/t-900-a/moneroodoo)
[![codecov](https://codecov.io/gh/t-900-a/moneroodoo/branch/master/graph/badge.svg)](https://codecov.io/gh/t-900-a/moneroodoo)


Allows you to accept Monero as Payment within your Odoo Ecommerce shop

**Table of contents**

.. contents::
   :local:

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
    * queue-job
        * https://github.com/OCA/queue
    * monero-rpc-odoo
        * https://github.com/monero-integrations/moneroodoo
        * The Monero payment acquirer is configured similar to other payment acquirers
            * https://www.odoo.com/documentation/user/14.0/general/payment_acquirers/payment_acquirers.html#configuration
    * Currency rate
      * You will need to manually add currency rate for Monero
      * https://www.odoo.com/documentation/user/14.0/accounting/others/multicurrencies/how_it_works.html
    * Pricelist
        * A pricelist should be created specifically for Monero
        * https://www.odoo.com/documentation/user/14.0/website/publish/multi_website.html#pricelists
    
    

Usage
=====

* At Ecommerce checkout your customer's will be presented with the option to pay 
  with Monero

Bug Tracker
===========

Bugs are tracked on `GitHub Issues <https://github.com/monero-integrations/moneroodoo/issues>`_.
In case of trouble, please check there if your issue has already been reported.
If you spotted it first, help us smashing it by providing a detailed and welcomed
`feedback <https://github.com/monero-integrations/moneroodoo/issues/new?
body=module:%20monero-rpc-odoo%0Aversion:%14.
0%0A%0A**Steps%20to%20reproduce**%0A-%20...%0A%0A**Current%20behavior**%0A%0A**Expected%20behavior**>`_.

Credits
=======

Authors
~~~~~~~

* T-900

Contributors
~~~~~~~~~~~~

* T-900 <https://github.com/t-900-a>

Maintainers
~~~~~~~~~~~

This module is maintained by Monero-Integrations.

.. image:: https://monerointegrations.com/img/monero-integrations-logo.png
   :alt: Monero Integrations
   :target: https://monerointegrations.com

.. |maintainer-t-900| image:: https://github.com/t-900-a.png?size=40px
    :target: https://github.com/t-900-a
    :alt: T-900

Current `maintainer `__:

|maintainer-t-900| 

This module is part of the `monero-integrations/moneroodoo <https://github.com/monero-integrations/moneroodoo>`_ project on GitHub.

You are welcome to contribute. To learn how please visit https://taiga.getmonero.org/project/t-900-monero-x-odoo-integrations/.
