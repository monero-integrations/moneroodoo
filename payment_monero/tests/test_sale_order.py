from typing import Any

from odoo.addons.website_sale.tests.common import TestWebsiteSaleCommon
from odoo.tests import tagged

from datetime import datetime
from unittest.mock import patch

from monero import MoneroAccount, MoneroTxWallet, MoneroBlock, MoneroIncomingTransfer, MoneroUtils

from ..models.exceptions import MoneroNoTransactionFoundError, MoneroNumConfirmationsNotMetError
from ..models.sale_order import MoneroSaleOrder


@tagged("post_install", "-at_install")
class TestMoneroSaleOrder(TestWebsiteSaleCommon):
    company_data: dict[str, Any] = {}

    class MockBackend(object):
        transfers: list[MoneroIncomingTransfer]
        
        def __init__(self, **kwargs):
            self.transfers = []
            tx = MoneroTxWallet()
            tx.block = MoneroBlock()
            tx.block.height = 1087606
            tx.hash = "a0b876ebcf7c1d499712d84cedec836f9d50b608bb22d6cb49fd2feae3ffed14"
            tx.fee = 352891
            tx.num_confirmations = 3
            tx.last_relayed_timestamp = int(datetime(2018, 1, 29, 15, 0, 25).timestamp())
            tx.payment_id = "0166d8da6c0045c51273dd65d6f63734beb8a84e0545a185b2cfd053fced9f5d"
            pm = MoneroIncomingTransfer()
            pm.amount = MoneroUtils.xmr_to_atomic_units(1)
            pm.tx = tx
            pm.address = "Bf6ngv7q2TBWup13nEm9AjZ36gLE6i4QCaZ7XScZUKDUeGbYEHmPRdegKGwLT8tBBK7P6L32RELNzCR6QzNFkmogDjvypyV"

            self.transfers.append(pm)

            tx = MoneroTxWallet()
            tx.block = MoneroBlock()
            tx.block.height = 1087530
            tx.hash = "5c3ab739346e9d98d38dc7b8d36a4b7b1e4b6a16276946485a69797dbf887cd8"
            tx.fee = MoneroUtils.xmr_to_atomic_units(0.000962550000)
            tx.last_relayed_timestamp = int(datetime(2018, 1, 29, 13, 17, 18).timestamp())
            tx.payment_id = "f75ad90e25d71a12"
            pm = MoneroIncomingTransfer()
            pm.amount = MoneroUtils.xmr_to_atomic_units(10)
            pm.address = "9tQoHWyZ4yXUgbz9nvMcFZUfDy5hxcdZabQCxmNCUukKYicXegsDL7nQpcUa3A1pF6K3fhq3scsyY88tdB1MqucULcKzWZC"
            pm.tx = tx

            self.transfers.append(pm)

            tx = MoneroTxWallet()
            tx.block = MoneroBlock()
            tx.block.height = 1087608
            tx.hash = "4ea70add5d0c7db33557551b15cd174972fcfc73bf0f6a6b47b7837564b708d3"
            tx.fee = MoneroUtils.xmr_to_atomic_units(0.000962550000)
            tx.num_confirmations = 1
            tx.last_relayed_timestamp = int(datetime(2018, 1, 29, 13, 17, 18).timestamp())
            tx.payment_id = "f75ad90e25d71a12"
            pm = MoneroIncomingTransfer()
            pm.amount = MoneroUtils.xmr_to_atomic_units(4)
            pm.address = "9tQoHWyZ4yXUgbz9nvMcFZUfDy5hxcdZabQCxmNCUukKYicXegsDL7nQpcUa3A1pF6K3fhq3scsyY88tdB1MqucULcKzWZC"
            pm.tx = tx

            self.transfers.append(pm)

            tx = MoneroTxWallet()
            tx.block = MoneroBlock()
            tx.block.height = 1087530
            tx.hash = "e9a71c01875bec20812f71d155bfabf42024fde3ec82475562b817dcc8cbf8dc"
            tx.fee = MoneroUtils.xmr_to_atomic_units(0.000962550000)
            tx.last_relayed_timestamp = int(datetime(2018, 1, 29, 13, 17, 18).timestamp())
            tx.payment_id = "cb248105ea6a9189"
            pm = MoneroIncomingTransfer()
            pm.amount = MoneroUtils.xmr_to_atomic_units(2.12)
            pm.address = "9tQoHWyZ4yXUgbz9nvMcFZUfDy5hxcdZabQCxmNCUukKYicXegsDL7nQpcUa3A1pF6K3fhq3scsyY88tdB1MqucULcKzWZC"
            pm.tx = tx

            self.transfers.append(pm)
            
            tx = MoneroTxWallet()
            tx.block = MoneroBlock()
            tx.block.height = 1087601
            tx.hash = "5ef7ead6a041101ed326568fbb59c128403cba46076c3f353cd110d969dac808"
            tx.fee = MoneroUtils.xmr_to_atomic_units(0.00096243)
            tx.payment_id = "0000000000000000"
            pm = MoneroIncomingTransfer()
            pm.amount = MoneroUtils.xmr_to_atomic_units(1240)
            pm.address = "BhE3cQvB7VF2uuXcpXp28Wbadez6GgjypdRS1F1Mzqn8Advd6q8VfaX8ZoEDobjejrMfpHeNXoX8MjY8q8prW1PEALgr1En"
            pm.tx = tx

            self.transfers.append(pm)

            tx = MoneroTxWallet()
            tx.block = MoneroBlock()
            tx.block.height = 1087606
            tx.hash = "cc44568337a186c2e1ccc080b43b4ae9db26a07b7afd7edeed60ce2fc4a6477f"
            tx.fee = MoneroUtils.xmr_to_atomic_units(0.000962550000)
            tx.payment_id = "0000000000000000"
            tx.last_relayed_timestamp = int(datetime(2018, 1, 29, 13, 17, 18).timestamp())
            pm = MoneroIncomingTransfer()
            pm.amount = MoneroUtils.xmr_to_atomic_units(10)
            pm.address = "9tQoHWyZ4yXUgbz9nvMcFZUfDy5hxcdZabQCxmNCUukKYicXegsDL7nQpcUa3A1pF6K3fhq3scsyY88tdB1MqucULcKzWZC"
            pm.tx = tx

            self.transfers.append(pm)

            tx = MoneroTxWallet()
            tx.hash = "d29264ad317e8fdb55ea04484c00420430c35be7b3fe6dd663f99aebf41a786c"
            tx.fee = MoneroUtils.xmr_to_atomic_units(0.000961950000)
            tx.last_relayed_timestamp = int(datetime(2018, 1, 29, 21, 13, 28).timestamp())
            tx.payment_id = "03f6649304ea4cb2"
            pm = MoneroIncomingTransfer()
            pm.amount = MoneroUtils.xmr_to_atomic_units(3.14)
            pm.address = "9tQoHWyZ4yXUgbz9nvMcFZUfDy5hxcdZabQCxmNCUukKYicXegsDL7nQpcUa3A1pF6K3fhq3scsyY88tdB1MqucULcKzWZC"
            pm.tx = tx
            
            self.transfers.append(pm)

        def height(self):
            return 1087607

        def accounts(self) -> list[MoneroAccount]:
            account = MoneroAccount()
            account.index = 0
            return [account]

        def transfers_in(self, account, pmtfilter):
            return list(pmtfilter.filter(self.transfers))

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref) # type: ignore

        SalesOrder = cls.env["sale.order"].with_context(tracking_disable=True)

        # set up users
        cls.crm_team0 = cls.env["crm.team"].create(
            {"name": "crm team 0", "company_id": cls.company_data["company"].id}
        )
        cls.crm_team1 = cls.env["crm.team"].create(
            {"name": "crm team 1", "company_id": cls.company_data["company"].id}
        )
        cls.user_in_team = cls.env["res.users"].create(
            {
                "email": "team0user@example.com",
                "login": "team0user",
                "name": "User in Team 0",
                "sale_team_id": cls.crm_team0.id,
            }
        )
        cls.user_not_in_team = cls.env["res.users"].create(
            {
                "email": "noteamuser@example.com",
                "login": "noteamuser",
                "name": "User Not In Team",
            }
        )

        # over ride the predefined partner, as it is missing a country id
        cls.partner_a = cls.env["res.partner"].create(
            {
                "name": "test",
                "email": "test@example.com",
                "country_id": 1,
            }
        )

        # create a generic Sale Order with all classical products and empty pricelist
        cls.sale_order = SalesOrder.create(
            {
                "partner_id": cls.partner_a.id,
                "partner_invoice_id": cls.partner_a.id,
                "partner_shipping_id": cls.partner_a.id,
                "pricelist_id": cls.company_data["default_pricelist"].id,
            }
        )
        cls.sol_product_order = cls.env["sale.order.line"].create(
            {
                "name": cls.company_data["product_order_no"].name,
                "product_id": cls.company_data["product_order_no"].id,
                "product_uom_qty": 2,
                "product_uom": cls.company_data["product_order_no"].uom_id.id,
                "price_unit": cls.company_data["product_order_no"].list_price,
                "order_id": cls.sale_order.id,
                "tax_id": False,
            }
        )
        cls.sol_serv_deliver = cls.env["sale.order.line"].create(
            {
                "name": cls.company_data["product_service_delivery"].name,
                "product_id": cls.company_data["product_service_delivery"].id,
                "product_uom_qty": 2,
                "product_uom": cls.company_data["product_service_delivery"].uom_id.id,
                "price_unit": cls.company_data["product_service_delivery"].list_price,
                "order_id": cls.sale_order.id,
                "tax_id": False,
            }
        )
        cls.sol_serv_order = cls.env["sale.order.line"].create(
            {
                "name": cls.company_data["product_service_order"].name,
                "product_id": cls.company_data["product_service_order"].id,
                "product_uom_qty": 2,
                "product_uom": cls.company_data["product_service_order"].uom_id.id,
                "price_unit": cls.company_data["product_service_order"].list_price,
                "order_id": cls.sale_order.id,
                "tax_id": False,
            }
        )
        cls.sol_product_deliver = cls.env["sale.order.line"].create(
            {
                "name": cls.company_data["product_delivery_no"].name,
                "product_id": cls.company_data["product_delivery_no"].id,
                "product_uom_qty": 2,
                "product_uom": cls.company_data["product_delivery_no"].uom_id.id,
                "price_unit": cls.company_data["product_delivery_no"].list_price,
                "order_id": cls.sale_order.id,
                "tax_id": False,
            }
        )

        # define payment acquirer
        cls.payment_acquirer = cls.env["payment.acquirer"].create(
            { "name": "Monero", "journal_id": 1 }
        )

    @patch("odoo.addons.payment_monero.models.monero_acq.JSONRPCWallet")
    def test_sale_order_process_transaction(self, mock_backend):
        """Test processing of monero transactions
        - The class: MoneroSaleOrder process_transaction defined to interface with
        the rpc wallet and if the transaction checks out the sales order and
        transaction states are updated
        """

        # current state: test runs and passes,
        # but only because we assertRaises(MoneroAddressReuse)
        # TODO test all exceptions
        # TODO test that a transaction is processed to completion

        # START MAIN TEST

        # define payment token
        payment_token = {
            "name": "BhE3cQvB7VF2uuXcpXp28Wbadez6GgjypdRS1F1Mzqn8Advd6q8VfaX8ZoEDobjejr"
            "MfpHeNXoX8MjY8q8prW1PEALgr1En",
            "partner_id": self.sale_order.partner_id.id,
            "active": False,
            "acquirer_id": self.payment_acquirer.id,
            "acquirer_ref": "payment.payment_acquirer_monero_rpc",
        }

        token = self.env["payment.token"].sudo().create(payment_token)

        # setup transaction
        tx_val = {
            "amount": self.sale_order.amount_total,
            "reference": self.sale_order.name + "main",
            "currency_id": self.sale_order.currency_id.id,
            "partner_id": self.partner_a.id,
            "payment_token_id": token.id,  # Associating the Payment Token ID.
            "acquirer_id": self.payment_acquirer.id,  # Payment Acquirer - Monero
            "state": "pending",
        }

        transaction = self.env["payment.transaction"].create(tx_val)

        mock_backend.side_effect = self.MockBackend

        num_confirmation_required = 0
        MoneroSaleOrder.process_transaction(
            self.sale_order, transaction, token, num_confirmation_required
        )
        self.assertEqual(self.sale_order.state, "sale")
        self.assertEqual(transaction.state, "done")

        # END MAIN TEST

        # START EXCEPTION TEST: MoneroAddressReuse

        # define payment token
        payment_token = {
            "name": "9tQoHWyZ4yXUgbz9nvMcFZUfDy5hxcdZabQCxmNCUukKYicXegsDL7nQpcUa3A1pF6"
            "K3fhq3scsyY88tdB1MqucULcKzWZC",
            "partner_id": self.sale_order.partner_id.id,
            "active": False,
            "acquirer_id": self.payment_acquirer.id,
            "acquirer_ref": "payment.payment_acquirer_monero_rpc",
        }

        token = self.env["payment.token"].sudo().create(payment_token)

        # setup transaction
        tx_val = {
            "amount": self.sale_order.amount_total,
            "reference": self.sale_order.name,
            "currency_id": self.sale_order.currency_id.id,
            "partner_id": self.partner_a.id,
            "payment_token_id": token.id,  # Associating the Payment Token ID.
            "acquirer_id": self.payment_acquirer.id,  # Payment Acquirer - Monero
            "state": "pending",
        }

        transaction = self.env["payment.transaction"].create(tx_val)

        mock_backend.side_effect = self.MockBackend

        num_confirmation_required = 0

        # END EXCEPTION TEST: MoneroAddressReuse

        # START EXCEPTION TEST: NumConfirmationsNotMet

        # define payment token
        payment_token = {
            "name": "Bf6ngv7q2TBWup13nEm9AjZ36gLE6i4QCaZ7XScZUKDUeGbYEHmPRdegKGwLT8tBBK"
            "7P6L32RELNzCR6QzNFkmogDjvypyV",
            "partner_id": self.sale_order.partner_id.id,
            "active": False,
            "acquirer_id": self.payment_acquirer.id,
            "acquirer_ref": "payment.payment_acquirer_monero_rpc",
        }

        token = self.env["payment.token"].sudo().create(payment_token)
        # setup transaction
        tx_val = {
            "amount": self.sale_order.amount_total,
            "reference": self.sale_order.name + "NumConfirmationsNotMet",
            "currency_id": self.sale_order.currency_id.id,
            "partner_id": self.partner_a.id,
            "payment_token_id": token.id,  # Associating the Payment Token ID.
            "acquirer_id": self.payment_acquirer.id,  # Payment Acquirer - Monero
            "state": "pending",
        }

        transaction = self.env["payment.transaction"].create(tx_val)

        mock_backend.side_effect = self.MockBackend

        num_confirmation_required = 10
        assertion = self.assertRaises(MoneroNumConfirmationsNotMetError)
        if assertion is not None:
            with assertion:
                MoneroSaleOrder.process_transaction(
                    self.sale_order, transaction, token, num_confirmation_required
                )

        # END EXCEPTION TEST: NumConfirmationsNotMet

        # START EXCEPTION TEST: NoTXFound

        # define payment token
        # this address doesn't exist, so there will be no transactions returned
        payment_token = {
            "name": "Bbvf3yAShddPnnhzUbzN4CLSaKaY8HG3kJ2pQUHiJx7ZfCDXHJ87M"
            "aZHWL13xKz7s9LESB4tWWFKsYAkrAd74K38Uw98cfc",
            "partner_id": self.sale_order.partner_id.id,
            "active": False,
            "acquirer_id": self.payment_acquirer.id,
            "acquirer_ref": "payment.payment_acquirer_monero_rpc",
        }

        token = self.env["payment.token"].sudo().create(payment_token)
        # setup transaction
        tx_val = {
            "amount": self.sale_order.amount_total,
            "reference": self.sale_order.name + "NoTXFound",
            "currency_id": self.sale_order.currency_id.id,
            "partner_id": self.partner_a.id,
            "payment_token_id": token.id,  # Associating the Payment Token ID.
            "acquirer_id": self.payment_acquirer.id,  # Payment Acquirer - Monero
            "state": "pending",
        }

        transaction = self.env["payment.transaction"].create(tx_val)

        mock_backend.side_effect = self.MockBackend

        num_confirmation_required = 10
        assertion = self.assertRaises(MoneroNoTransactionFoundError)
        if assertion is not None:
            with assertion:
                MoneroSaleOrder.process_transaction(
                    self.sale_order, transaction, token, num_confirmation_required
                )

        # END EXCEPTION TEST: NoTXFound
