import logging

import requests as http_requests

from odoo import models

from ..models.exceptions import NoTXFound, NumConfirmationsNotMet
from ..models.exceptions import MoneroPaymentAcquirerRPCUnauthorized
from ..models.exceptions import MoneroPaymentAcquirerRPCSSLError

_logger = logging.getLogger(__name__)

# XMR uses 12 decimal places; 1 XMR = 1_000_000_000_000 piconero
PICONERO = 1_000_000_000_000


class MoneroSalesOrder(models.Model):
    _inherit = "sale.order"

    def process_transaction(self, transaction, num_confirmation_required):
        """
        Poll the Monero wallet RPC for an incoming payment to the subaddress
        stored in transaction.provider_reference.

        Uses get_balance RPC directly because monero-python's wallet.incoming()
        returns the primary address for all transfers, not the subaddress.

        :param payment.transaction transaction: The pending Monero transaction.
        :param int num_confirmation_required: Number of confirmations required.
        """
        # If already confirmed, nothing to do
        if transaction.state == 'done':
            return

        # If the sale order was deleted, skip silently
        if not self.exists():
            _logger.info(f"Monero cron: sale order no longer exists, skipping.")
            return

        subaddress = transaction.provider_reference
        provider = transaction.provider_id

        # Build RPC URL from provider config
        rpc_url = (
            f"{provider.rpc_protocol}://"
            f"{provider.monero_rpc_config_host}:"
            f"{provider.monero_rpc_config_port}/json_rpc"
        )
        rpc_auth = None
        if provider.monero_rpc_config_user:
            rpc_auth = (
                provider.monero_rpc_config_user,
                provider.monero_rpc_config_password or '',
            )

        try:
            resp = http_requests.post(
                rpc_url,
                json={
                    'jsonrpc': '2.0',
                    'id': '0',
                    'method': 'get_balance',
                    'params': {'account_index': 0, 'all_accounts': False},
                },
                auth=rpc_auth,
                timeout=10,
            )
            resp.raise_for_status()
            result = resp.json().get('result', {})
        except http_requests.exceptions.ConnectionError:
            raise MoneroPaymentAcquirerRPCUnauthorized(
                "Monero RPC: connection refused"
            )
        except Exception as e:
            raise Exception(
                f"Monero RPC error: {e.__class__.__name__}: {e}"
            )

        per_subaddress = result.get('per_subaddress', [])

        # Find the entry for our specific subaddress
        sub_entry = next(
            (s for s in per_subaddress if s.get('address') == subaddress),
            None
        )

        if sub_entry is None or sub_entry.get('balance', 0) == 0:
            # No payment received yet
            cron_id = self.env.context.get('cron_id')
            if cron_id:
                cron = self.env['ir.cron'].browse(cron_id)
                if cron.failure_count >= 60:  # ~1 hour of retries
                    if self.exists():
                        self.write({"state": "cancel"})
                    _logger.warning(
                        f"Monero: no payment after 60 retries for order {self.id}, "
                        f"subaddress {subaddress}. Cancelling."
                    )
                    return

            raise NoTXFound(
                f"PaymentProvider: {provider.code} "
                f"Subaddress: {subaddress} "
                "Status: No payment found yet. "
                "Another job will execute. Action: Nothing"
            )

        # Payment found — check confirmations if required
        if num_confirmation_required > 0:
            unlocked = sub_entry.get('unlocked_balance', 0)
            balance = sub_entry.get('balance', 0)
            if unlocked < balance:
                raise NumConfirmationsNotMet(
                    f"PaymentProvider: {provider.code} "
                    f"Subaddress: {subaddress} "
                    f"Status: Waiting for confirmations. "
                    f"Balance: {balance/PICONERO}, Unlocked: {unlocked/PICONERO}"
                )

        # Use unlocked_balance if confirmations required, else balance
        if num_confirmation_required > 0:
            received_piconero = sub_entry.get('unlocked_balance', 0)
        else:
            received_piconero = sub_entry.get('balance', 0)

        # Use monero_amount_xmr (the exact XMR amount at checkout) if available,
        # otherwise fall back to tx.amount (which may be in USD).
        xmr_expected = transaction.monero_amount_xmr or transaction.amount
        expected_piconero = int(round(float(xmr_expected) * PICONERO))
        received = received_piconero / PICONERO
        expected = expected_piconero / PICONERO

        _logger.info(
            f"Monero payment check: subaddress={subaddress}, "
            f"received={received} XMR, expected={expected} XMR"
        )

        if received_piconero >= expected_piconero:
            transaction._set_done()
            # Confirm the sale order directly.
            # We skip _post_process() because it requires an accounting
            # payment method line on the journal, which is not needed for
            # a crypto payment. The transaction state change to 'done' is
            # enough for the /payment/status JS to redirect the buyer.
            if self.exists() and self.state in ('draft', 'sent'):
                self.action_confirm()
            _logger.info(
                f"Monero payment confirmed for sale order {self.id}, "
                f"subaddress {subaddress}, received {received} XMR"
            )
            # Note: we do not deactivate the cron here because Odoo locks
            # the cron record while it is running. The 'done' guard at the
            # top of this method ensures subsequent runs are no-ops.
        else:
            _logger.warning(
                f"Monero underpayment for order {self.id}: "
                f"expected {expected} XMR, received {received} XMR"
            )
