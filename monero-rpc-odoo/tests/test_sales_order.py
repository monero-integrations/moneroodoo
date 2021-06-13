from odoo.tests import tagged

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch
from ..models.exceptions import NoTXFound, NumConfirmationsNotMet, MoneroAddressReuse

from monero.account import Account
from monero.address import address
from monero.numbers import PaymentID
from monero.transaction import IncomingPayment, Transaction

from ..models.sales_order import MoneroSalesOrder

from odoo.addons.sale.tests.common import TestSaleCommon


@tagged("post_install", "-at_install")
class TestMoneroSalesOrder(TestSaleCommon):
    class MockBackend(object):
        def __init__(self, **kwargs):
            self.transfers = []
            tx = Transaction(
                timestamp=datetime(2018, 1, 29, 15, 0, 25),
                height=1087606,
                hash="a0b876ebcf7c1d499712d84cedec836f9d50b608bb22d6cb49fd2feae3ffed14",
                fee=Decimal("0.00352891"),
                confirmations=3,
            )
            pm = IncomingPayment(
                amount=Decimal("1"),
                local_address=address(
                    "Bf6ngv7q2TBWup13nEm9AjZ36gLE6i4QCaZ7XScZUKDUeGbYEHmPRdegKGwLT8tBBK"
                    "7P6L32RELNzCR6QzNFkmogDjvypyV"
                ),
                payment_id=PaymentID(
                    "0166d8da6c0045c51273dd65d6f63734beb8a84e0545a185b2cfd053fced9f5d"
                ),
                transaction=tx,
            )
            self.transfers.append(pm)
            tx = Transaction(
                timestamp=datetime(2018, 1, 29, 13, 17, 18),
                height=1087530,
                hash="5c3ab739346e9d98d38dc7b8d36a4b7b1e4b6a16276946485a69797dbf887cd8",
                fee=Decimal("0.000962550000"),
            )
            pm = IncomingPayment(
                amount=Decimal("10.000000000000"),
                local_address=address(
                    "9tQoHWyZ4yXUgbz9nvMcFZUfDy5hxcdZabQCxmNCUukKYicXegsDL7nQpcUa3A1pF6"
                    "K3fhq3scsyY88tdB1MqucULcKzWZC"
                ),
                payment_id=PaymentID("f75ad90e25d71a12"),
                transaction=tx,
            )
            self.transfers.append(pm)
            tx = Transaction(
                timestamp=datetime(2018, 1, 29, 13, 17, 18),
                height=1087608,
                hash="4ea70add5d0c7db33557551b15cd174972fcfc73bf0f6a6b47b7837564b708d3",
                fee=Decimal("0.000962550000"),
                confirmations=1,
            )
            pm = IncomingPayment(
                amount=Decimal("4.000000000000"),
                local_address=address(
                    "9tQoHWyZ4yXUgbz9nvMcFZUfDy5hxcdZabQCxmNCUukKYicXegsDL7nQpcUa3A1pF6"
                    "K3fhq3scsyY88tdB1MqucULcKzWZC"
                ),
                payment_id=PaymentID("f75ad90e25d71a12"),
                transaction=tx,
            )
            self.transfers.append(pm)
            tx = Transaction(
                timestamp=datetime(2018, 1, 29, 13, 17, 18),
                height=1087530,
                hash="e9a71c01875bec20812f71d155bfabf42024fde3ec82475562b817dcc8cbf8dc",
                fee=Decimal("0.000962550000"),
            )
            pm = IncomingPayment(
                amount=Decimal("2.120000000000"),
                local_address=address(
                    "9tQoHWyZ4yXUgbz9nvMcFZUfDy5hxcdZabQCxmNCUukKYicXegsDL7nQpcUa3A1pF6"
                    "K3fhq3scsyY88tdB1MqucULcKzWZC"
                ),
                payment_id=PaymentID("cb248105ea6a9189"),
                transaction=tx,
            )
            self.transfers.append(pm)
            tx = Transaction(
                timestamp=datetime(2018, 1, 29, 14, 57, 47),
                height=1087601,
                hash="5ef7ead6a041101ed326568fbb59c128403cba46076c3f353cd110d969dac808",
                fee=Decimal("0.000962430000"),
            )
            pm = IncomingPayment(
                amount=Decimal("1240.0000000"),
                local_address=address(
                    "BhE3cQvB7VF2uuXcpXp28Wbadez6GgjypdRS1F1Mzqn8Advd6q8VfaX8ZoEDobjejr"
                    "MfpHeNXoX8MjY8q8prW1PEALgr1En"
                ),
                payment_id=PaymentID("0000000000000000"),
                transaction=tx,
            )
            self.transfers.append(pm)
            tx = Transaction(
                timestamp=datetime(2018, 1, 29, 13, 17, 18),
                height=1087606,
                hash="cc44568337a186c2e1ccc080b43b4ae9db26a07b7afd7edeed60ce2fc4a6477f",
                fee=Decimal("0.000962550000"),
            )
            pm = IncomingPayment(
                amount=Decimal("10.000000000000"),
                local_address=address(
                    "9tQoHWyZ4yXUgbz9nvMcFZUfDy5hxcdZabQCxmNCUukKYicXegsDL7nQpcUa3A1pF6"
                    "K3fhq3scsyY88tdB1MqucULcKzWZC"
                ),
                payment_id=PaymentID("0000000000000000"),
                transaction=tx,
            )
            self.transfers.append(pm)
            tx = Transaction(
                timestamp=datetime(2018, 1, 29, 21, 13, 28),
                height=None,
                hash="d29264ad317e8fdb55ea04484c00420430c35be7b3fe6dd663f99aebf41a786c",
                fee=Decimal("0.000961950000"),
            )
            pm = IncomingPayment(
                amount=Decimal("3.140000000000"),
                local_address=address(
                    "9tQoHWyZ4yXUgbz9nvMcFZUfDy5hxcdZabQCxmNCUukKYicXegsDL7nQpcUa3A1pF6"
                    "K3fhq3scsyY88tdB1MqucULcKzWZC"
                ),
                payment_id=PaymentID("03f6649304ea4cb2"),
                transaction=tx,
            )
            self.transfers.append(pm)

        def height(self):
            return 1087607

        def accounts(self):
            return [Account(self, 0)]

        def transfers_in(self, account, pmtfilter):
            return list(pmtfilter.filter(self.transfers))

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)

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
            {"name": "Monero RPC", "journal_id": 1}
        )

    @patch("odoo.addons.monero-rpc-odoo.models.monero_acq.JSONRPCWallet")
    def test_sale_order_process_transaction(self, mock_backend):
        """Test processing of monero transactions
        - The class: MoneroSalesOrder process_transaction defined to interface with
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
        MoneroSalesOrder.process_transaction(
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
        with self.assertRaises(MoneroAddressReuse):
            MoneroSalesOrder.process_transaction(
                self.sale_order, transaction, token, num_confirmation_required
            )

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
        with self.assertRaises(NumConfirmationsNotMet):
            MoneroSalesOrder.process_transaction(
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
        with self.assertRaises(NoTXFound):
            MoneroSalesOrder.process_transaction(
                self.sale_order, transaction, token, num_confirmation_required
            )

        # END EXCEPTION TEST: NoTXFound
