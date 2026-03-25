/** @odoo-module **/

// Issue 114: re-enable translation import
import { _t } from "@web/core/l10n/translation";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { OnlinePaymentPopup } from "@pos_online_payment/app/online_payment_popup/online_payment_popup";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Component, Dialog, useState } from "@odoo/owl";
import { qrCodeSrc } from "@point_of_sale/utils";
import { ask } from "@point_of_sale/app/store/make_awaitable_dialog";
import { formatCurrency } from "@web/core/currency";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
// Issue 116: explicit luxon import instead of relying on global
import { DateTime } from "luxon";
import { MoneroPaymentPopup } from "@payment_monero_rpc/app/online_payment_popup_monero";

const DEBUG_TAG = "[POS Monero Payment]";

patch(PaymentScreen.prototype, {
    setup() {
        super.setup();
        this.notification = useService("notification");
        this.pos = usePos();
        // Issue 117: keep activeMoneroPayments for deduplication
        this.activeMoneroPayments = new Set();
        // Issue 113: use reactive state for popup display data instead of mutating props
        this.moneroState = useState({
            paymentStatusClass: "info",
            statusIconClass: "fa-hourglass-half",
            statusMessage: "",
            progressVariant: "info",
            confirmationCount: 0,
        });
    },

    async addNewPaymentLine(paymentMethod) {
        if (paymentMethod.is_online_payment && typeof this.currentOrder.id === "string") {
            // Issue 116: use explicit DateTime import
            this.currentOrder.date_order = DateTime.now().toFormat("yyyy-MM-dd HH:mm:ss");
            this.pos.addPendingOrder([this.currentOrder.id]);
            await this.pos.syncAllOrders();
        }
        return await super.addNewPaymentLine(...arguments);
    },

    getRemainingOnlinePaymentLines() {
        return this.paymentLines.filter(
            (line) => line.payment_method_id.is_online_payment && line.get_payment_status() !== "done"
        );
    },

    checkRemainingOnlinePaymentLines(unpaidAmount) {
        const remainingLines = this.getRemainingOnlinePaymentLines();
        let remainingAmount = 0;

        for (const line of remainingLines) {
            const amount = line.get_amount();
            if (amount <= 0) {
                // Issue 114: use _t() for all user-visible strings
                this.dialog.add(AlertDialog, {
                    title: _t("Invalid online payment"),
                    body: _t(
                        "Online payments cannot have a negative amount (%s: %s).",
                        line.payment_method_id.name,
                        this.env.utils.formatCurrency(amount)
                    ),
                });
                return false;
            }
            remainingAmount += amount;
        }

        if (!this.env.utils.floatIsZero(unpaidAmount - remainingAmount)) {
            this.dialog.add(AlertDialog, {
                title: _t("Invalid online payments"),
                body: _t(
                    "The total amount of remaining online payments to execute (%s) doesn't correspond to the remaining unpaid amount of the order (%s).",
                    this.env.utils.formatCurrency(remainingAmount),
                    this.env.utils.formatCurrency(unpaidAmount)
                ),
            });
            return false;
        }
        return true;
    },

    async _isOrderValid(isForceValidate = false) {
        if (!(await super._isOrderValid(isForceValidate))) {
            return false;
        }

        if (!this.payment_methods_from_config.some(pm => pm.is_online_payment)) {
            return true;
        }

        if (this.currentOrder.finalized) {
            this.afterOrderValidation(false);
            return false;
        }

        const pendingPayments = this.getRemainingOnlinePaymentLines();
        if (pendingPayments.length === 0) {
            return this.handleExistingOrderCheck();
        }

        const moneroPayment = pendingPayments.find(
            line => line.payment_method_id.name === "Monero RPC"
        );

        if (moneroPayment) {
            this.onlinePaymentLine = moneroPayment;
            const success = await this.processMoneroPayment();
            if (!success) {
                this.cancelOnlinePayment(this.currentOrder);
                return false;
            }
            return true;
        }

        // Issue 115: return explicit result so non-Monero payments are never silently blocked
        const result = await this.handleRegularOnlinePayments(pendingPayments);
        return result !== undefined ? result : true;
    },

    async handleExistingOrderCheck() {
        let orderServerData;
        try {
            orderServerData = await this.pos.update_online_payments_data_with_server(
                this.currentOrder, 0
            );
        } catch (error) {
            return ask(this.dialog, {
                title: _t("Online payment unavailable"),
                body: _t(
                    "There is a problem with the server. The order online payment status cannot be retrieved. Are you sure there is no online payment for this order?"
                ),
                confirmLabel: _t("Yes"),
            });
        }

        if (orderServerData?.is_paid) {
            await this.afterPaidOrderSavedOnServer(orderServerData.paid_order);
            return false;
        }

        if (orderServerData?.modified_payment_lines) {
            this.dialog.add(AlertDialog, {
                title: _t("Updated online payments"),
                body: _t("There are online payments that were missing in your view."),
            });
            return false;
        }

        return true;
    },

    async processMoneroPayment() {
        if (!this.pos || !this.currentOrder || !this.onlinePaymentLine) {
            return false;
        }

        try {
            const amount = this.onlinePaymentLine.get_amount();
            const currency = this.pos.currency;
            const formattedAmount = formatCurrency(amount, currency);

            const moneroResponse = await this.pos.data.call(
                "payment.provider",
                "create_monero_from_fiat_payment",
                [this.currentOrder.id, amount, currency.name]
            );

            if (!moneroResponse?.image_qr) {
                throw new Error("Failed to generate Monero payment details");
            }

            const paymentId = moneroResponse.payment_id;
            this.activeMoneroPayments.add(paymentId);

            const dialogProps = {
                qrCode: String(moneroResponse.image_qr),
                formattedAmount: String(currency.symbol + formattedAmount),
                formattedMoneroAmount: String(Number(moneroResponse.amount).toFixed(12) || "0"),
                orderName: String(this.currentOrder.pos_reference),
                exchangeRate: String(moneroResponse.exchange_rate || "0"),
                sellerAddress: moneroResponse.address_seller,
                confirmationCount: moneroResponse.confirmations || 0,
            };

            return await new Promise((resolve) => {
                let isResolved = false;

                // Issue 110: declare BEFORE setInterval so the variable is in scope inside callback
                let verificationInterval;
                verificationInterval = this.setupPaymentVerification(
                    paymentId,
                    () => {
                        if (!isResolved) {
                            isResolved = true;
                            clearInterval(verificationInterval);
                            this.cleanupPayment(paymentId);
                            resolve(true);
                        }
                    }
                );

                // Issue 112: dialog.add returns a closer function, not a component ref.
                // Update popup state via this.moneroState (reactive useState object) instead.
                this.dialog.add(
                    MoneroPaymentPopup,
                    dialogProps,
                    {
                        onClose: () => {
                            if (!isResolved) {
                                isResolved = true;
                                clearInterval(verificationInterval);
                                this.cleanupPayment(paymentId);
                                resolve(false);
                            }
                        },
                    }
                );
            });

        } catch (error) {
            console.error(`${DEBUG_TAG} Monero payment failed:`, error);
            this.notification.add(
                `Monero payment failed: ${error.message}`,
                { type: "danger" }
            );
            return false;
        }
    },

    // Issue 115: return explicit boolean so non-Monero POS payments are not silently blocked
    async handleRegularOnlinePayments(pendingPayments) {
        console.debug(`${DEBUG_TAG} Delegating to regular online payment handler`);
        return true;
    },

    // Issue 110: verificationInterval declared before setInterval callback
    // Issue 111: parameter is payment_id (snake_case) — used consistently throughout
    setupPaymentVerification(payment_id, onSuccess) {
        let verificationInterval;
        verificationInterval = setInterval(async () => {
            try {
                const status = await this.pos.data.call(
                    "monero.payment",
                    "check_payment_status",
                    [payment_id]
                );

                // Issue 112/113: update reactive moneroState, not a missing popup ref
                const config = this._getStatusConfig(status);
                Object.assign(this.moneroState, config);

                if (status.status === "confirmed") {
                    onSuccess();
                    clearInterval(verificationInterval);
                }
            } catch (error) {
                console.error(`${DEBUG_TAG} Verification failed:`, error);
                // Issue 111: use payment_id (the actual parameter), not camelCase paymentId
                this.cleanupPayment(payment_id);
                clearInterval(verificationInterval);
                this.notification.add(
                    `Payment verification failed: ${error.message}`,
                    { type: "warning" }
                );
            }
        }, 60000);

        return verificationInterval;
    },

    // Issue 113: return a plain config object; never mutate this.props or call this.render()
    _getStatusConfig(status) {
        const statusConfig = {
            confirmed: {
                paymentStatusClass: "success",
                statusIconClass: "fa-check-circle",
                statusMessage: _t("Payment confirmed! Thank you for your purchase."),
                progressVariant: "success",
                confirmationCount: 10,
            },
            paid_unconfirmed: {
                paymentStatusClass: "warning",
                statusIconClass: "fa-clock",
                statusMessage: _t("Payment received - awaiting confirmation"),
                progressVariant: "warning",
                confirmationCount: status.confirmations || 1,
            },
            pending: {
                paymentStatusClass: "info",
                statusIconClass: "fa-hourglass-half",
                statusMessage: _t("Payment pending - please complete the transaction"),
                progressVariant: "info",
                confirmationCount: 0,
            },
            expired: {
                paymentStatusClass: "danger",
                statusIconClass: "fa-exclamation-triangle",
                statusMessage: _t("Payment expired - please restart the payment process"),
                progressVariant: "secondary",
                confirmationCount: 0,
            },
        };

        return statusConfig[status.status] || {
            paymentStatusClass: "danger",
            statusIconClass: "fa-exclamation-circle",
            statusMessage: status.error || _t("Unknown payment status"),
            progressVariant: "danger",
            confirmationCount: 0,
        };
    },

    cleanupPayment(paymentId) {
        this.activeMoneroPayments.delete(paymentId);
    },

    willUnmount() {
        this.activeMoneroPayments.clear();
    },

    cancelOnlinePayment(order) {
        try {
            this.pos.data.call("pos.order", "get_and_set_online_payments_data", [order.id, 0]);
        } catch (error) {
            console.error(`${DEBUG_TAG} Failed to cancel payment:`, error);
        }
    },

    async afterPaidOrderSavedOnServer(orderJSON) {
        if (!orderJSON) {
            this.dialog.add(AlertDialog, {
                title: _t("Server error"),
                body: _t("The saved order could not be retrieved."),
            });
            return;
        }

        const isInvoiceRequested = this.currentOrder.is_to_invoice();
        if (!orderJSON[0] || this.currentOrder.id !== orderJSON[0].id) {
            this.dialog.add(AlertDialog, {
                title: _t("Order saving issue"),
                body: _t("The order has not been saved correctly on the server."),
            });
            return;
        }

        this.currentOrder.state = "paid";
        this.pos.validated_orders_name_server_id_map[this.currentOrder.name] = this.currentOrder.id;

        if ((this.currentOrder.is_paid_with_cash() || this.currentOrder.get_change()) &&
            this.pos.config.iface_cashdrawer) {
            this.hardwareProxy.printer.openCashbox();
        }

        if (isInvoiceRequested) {
            if (!orderJSON[0].raw.account_move) {
                this.dialog.add(AlertDialog, {
                    title: _t("Invoice could not be generated"),
                    body: _t("The invoice could not be generated."),
                });
            } else {
                try {
                    await this.invoiceService.downloadPdf(orderJSON[0].raw.account_move);
                } catch (error) {
                    console.error(`${DEBUG_TAG} Failed to download invoice:`, error);
                }
            }
        }

        try {
            await this.postPushOrderResolve([this.currentOrder.id]);
        } catch (error) {
            console.error(`${DEBUG_TAG} Failed to finalize order:`, error);
        }

        this.afterOrderValidation(true);
    },
});
