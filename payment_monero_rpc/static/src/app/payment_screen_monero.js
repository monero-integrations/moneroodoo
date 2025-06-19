/** @odoo-module **/

// import { _t } from "@web/core/l10n/translation"; // Disabled translation
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { OnlinePaymentPopup } from "@pos_online_payment/app/online_payment_popup/online_payment_popup";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Component, Dialog } from "@odoo/owl";
import { qrCodeSrc } from "@point_of_sale/utils";
import { ask } from "@point_of_sale/app/store/make_awaitable_dialog";
import { formatCurrency } from "@web/core/currency";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { MoneroPaymentPopup } from "@payment_monero_rpc/app/online_payment_popup_monero";

const DEBUG_TAG = "[POS Monero Payment]";

patch(PaymentScreen.prototype, {
    setup() {
        super.setup();
        this.notification = useService("notification");
        this.pos = usePos();
        this.activeMoneroPayments = new Set();        
    },
    async addNewPaymentLine(paymentMethod) {
        console.debug(`${DEBUG_TAG} addNewPaymentLine called with payment method:`, paymentMethod);
        if (paymentMethod.is_online_payment && typeof this.currentOrder.id === "string") {
            console.debug(`${DEBUG_TAG} Processing online payment for order:`, this.currentOrder.id);
            this.currentOrder.date_order = luxon.DateTime.now().toFormat("yyyy-MM-dd HH:mm:ss");
            this.pos.addPendingOrder([this.currentOrder.id]);
            await this.pos.syncAllOrders();
        }
        return await super.addNewPaymentLine(...arguments);
    },

    getRemainingOnlinePaymentLines() {
        const remainingLines = this.paymentLines.filter(
            (line) => line.payment_method_id.is_online_payment && line.get_payment_status() !== "done"
        );
        console.debug(`${DEBUG_TAG} Found ${remainingLines.length} remaining online payment lines`);
        return remainingLines;
    },

    checkRemainingOnlinePaymentLines(unpaidAmount) {
        console.debug(`${DEBUG_TAG} Checking remaining online payments against unpaid amount:`, unpaidAmount);
        const remainingLines = this.getRemainingOnlinePaymentLines();
        let remainingAmount = 0;
        
        for (const line of remainingLines) {
            const amount = line.get_amount();
            if (amount <= 0) {
                console.error(`${DEBUG_TAG} Invalid negative amount in online payment:`, amount);
                this.dialog.add(AlertDialog, {
                    // title: _t("Invalid online payment"),
                    title: "Invalid online payment",
                    // body: _t(
                    //     "Online payments cannot have a negative amount (%s: %s).",
                    //     line.payment_method_id.name,
                    //     this.env.utils.formatCurrency(amount)
                    // ),
                    body: `Online payments cannot have a negative amount (${line.payment_method_id.name}: ${this.env.utils.formatCurrency(amount)}).`,
                });
                return false;
            }
            remainingAmount += amount;
        }

        if (!this.env.utils.floatIsZero(unpaidAmount - remainingAmount)) {
            console.error(`${DEBUG_TAG} Payment amount mismatch. Remaining: ${remainingAmount}, Unpaid: ${unpaidAmount}`);
            this.dialog.add(AlertDialog, {
                // title: _t("Invalid online payments"),
                title: "Invalid online payments",
                // body: _t(
                //     "The total amount of remaining online payments to execute (%s) doesn't correspond to the remaining unpaid amount of the order (%s).",
                //     this.env.utils.formatCurrency(remainingAmount),
                //     this.env.utils.formatCurrency(unpaidAmount)
                // ),
                body: `The total amount of remaining online payments to execute (${this.env.utils.formatCurrency(remainingAmount)}) doesn't correspond to the remaining unpaid amount of the order (${this.env.utils.formatCurrency(unpaidAmount)}).`,
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

        return this.handleRegularOnlinePayments(pendingPayments);
    },

    async handleExistingOrderCheck() {
        console.debug(`${DEBUG_TAG} Checking existing order for payments`);
        let orderServerData;
        try {
            orderServerData = await this.pos.update_online_payments_data_with_server(
                this.currentOrder,
                0
            );
            console.debug(`${DEBUG_TAG} Existing order status:`, orderServerData);
        } catch (error) {
            console.error(`${DEBUG_TAG} Failed to check existing order:`, error);
            return ask(this.dialog, {
                // title: _t("Online payment unavailable"),
                title: "Online payment unavailable",
                // body: _t(
                //     "There is a problem with the server. The order online payment status cannot be retrieved. Are you sure there is no online payment for this order ?"
                // ),
                body: "There is a problem with the server. The order online payment status cannot be retrieved. Are you sure there is no online payment for this order?",
                // confirmLabel: _t("Yes"),
                confirmLabel: "Yes",
            });
        }

        if (orderServerData?.is_paid) {
            console.debug(`${DEBUG_TAG} Order is already paid`);
            await this.afterPaidOrderSavedOnServer(orderServerData.paid_order);
            return false;
        }

        if (orderServerData?.modified_payment_lines) {
            console.warn(`${DEBUG_TAG} Server reported modified payment lines`);
            this.dialog.add(AlertDialog, {
                // title: _t("Updated online payments"),
                title: "Updated online payments",
                // body: _t("There are online payments that were missing in your view."),
                body: "There are online payments that were missing in your view.",
            });
            return false;
        }

        return true;
    },

    async processMoneroPayment() {
        if (!this.pos || !this.currentOrder || !this.onlinePaymentLine) {
            console.error(`${DEBUG_TAG} Missing required payment context`);
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

            console.debug(`${DEBUG_TAG} Showing Monero payment dialog `, moneroResponse);
            
            const paymentId = moneroResponse.payment_id;
            console.debug(`${DEBUG_TAG} Received payment_id - `, paymentId);
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
                const verificationInterval = this.setupPaymentVerification(
                    paymentId,
                    () => {
                        if (!isResolved) {
                            isResolved = true;
                            this.cleanupPayment(paymentId);
                            resolve(true);
                        }
                    }
                );

                const closer = this.dialog.add(
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

    handleRegularOnlinePayments(pendingPayments) {
        console.debug(`${DEBUG_TAG} Under no circumstances should we get here!!!`);
    },

    setupPaymentVerification(payment_id, onSuccess) {
        return setInterval(async () => {
            try {
                console.log(`${DEBUG_TAG} Payment ID being sent:`, payment_id);
                const status = await this.pos.data.call(
                    "monero.payment",
                    "check_payment_status",
                    [payment_id]
                );
                
                 Object.assign(this.moneroPaymentPopup.props, this._getStatusConfig(status));                

                if (status.status == 'confirmed') {
                    onSuccess();
                    clearInterval(verificationInterval);
                }
            } catch (error) {
                console.error(`${DEBUG_TAG} Verification failed:`, error);
                this.cleanupPayment(paymentId);
                clearInterval(verificationInterval);
                // Optionally notify user
                this.notification.add(
                    `Payment verification failed: ${error.message}`,
                    { type: "warning" }
                );
            }
        }, 60000);
    },

    _getStatusConfig: function(status) {
        console.debug(`${DEBUG_TAG} Update screen data with - `, status);

        const statusConfig = {
            confirmed: {
                paymentStatusClass: 'success',
                statusIconClass: 'fa-check-circle',
                statusMessage: 'Payment confirmed! Thank you for your purchase.',
                progressVariant: 'success',
                progressWidth: '90%',
                progressHeight: '12px',
                stepPercentage: 10,
                confirmationCount: 10  // Fully confirmed
            },
            paid_unconfirmed: {
                paymentStatusClass: 'warning',
                statusIconClass: 'fa-clock',
                statusMessage: 'Payment received - awaiting confirmation',
                progressVariant: 'warning',
                progressWidth: '90%',
                progressHeight: '12px',
                stepPercentage: 10,
                confirmationCount: status.confirmations || 1  // Partial progress
            },
            pending: {
                paymentStatusClass: 'info',
                statusIconClass: 'fa-hourglass-half',
                statusMessage: 'Payment pending - please complete the transaction',
                progressVariant: 'info',
                progressWidth: '90%',
                progressHeight: '8px',  // Thinner as it's not started
                stepPercentage: 10,
                confirmationCount: 0  // No progress yet
            },
            expired: {
                paymentStatusClass: 'danger',
                statusIconClass: 'fa-exclamation-triangle',
                statusMessage: 'Payment expired - please restart the payment process',
                progressVariant: 'secondary',
                progressWidth: '90%',
                progressHeight: '8px',
                stepPercentage: 10,
                confirmationCount: 0,  // Reset progress
                additionalMessage: 'The payment session has expired. Please initiate a new payment.'
            }
        };

        // Get configuration for current status or default to error state
        const config = statusConfig[status.status] || {
            paymentStatusClass: 'danger',
            statusIconClass: 'fa-exclamation-circle',
            statusMessage: status.error || 'Unknown payment status',
            progressVariant: 'danger',
            progressWidth: '90%',
            progressHeight: '8px',
            confirmationCount: 0
        };

        // Update all props at once
        this.props = {
            ...this.props,
            ...config,
            // Preserve existing props that aren't being updated
            qrCode: this.props.qrCode,
            formattedAmount: this.props.formattedAmount,
            formattedMoneroAmount: this.props.formattedMoneroAmount,
            exchangeRate: this.props.exchangeRate,
            orderName: this.props.orderName,
            sellerAddress: this.props.sellerAddress
        };

        // Special case for expired status to show additional message
        if (status.status === 'expired') {
            this.props.statusMessage += ' ' + config.additionalMessage;
        }

        // Render the updated component
        this.render();
    },    

    cleanupPayment(paymentId) {
        this.activeMoneroPayments.delete(paymentId);
    },

    willUnmount() {
        this.activeMoneroPayments.clear();
    },

    cancelOnlinePayment(order) {
        console.debug(`${DEBUG_TAG} Canceling online payment for order:`, order.id);
        try {
            this.pos.data.call("pos.order", "get_and_set_online_payments_data", [order.id, 0]);
        } catch (error) {
            console.error(`${DEBUG_TAG} Failed to cancel payment:`, error);
        }
    },

    async afterPaidOrderSavedOnServer(orderJSON) {
        console.debug(`${DEBUG_TAG} Processing paid order:`, orderJSON);
        if (!orderJSON) {
            console.error(`${DEBUG_TAG} No order data received`);
            this.dialog.add(AlertDialog, {
                // title: _t("Server error"),
                title: "Server error",
                // body: _t("The saved order could not be retrieved."),
                body: "The saved order could not be retrieved.",
            });
            return;
        }

        const isInvoiceRequested = this.currentOrder.is_to_invoice();
        if (!orderJSON[0] || this.currentOrder.id !== orderJSON[0].id) {
            console.error(`${DEBUG_TAG} Order ID mismatch`);
            this.dialog.add(AlertDialog, {
                // title: _t("Order saving issue"),
                title: "Order saving issue",
                // body: _t("The order has not been saved correctly on the server."),
                body: "The order has not been saved correctly on the server.",
            });
            return;
        }

        this.currentOrder.state = "paid";
        this.pos.validated_orders_name_server_id_map[this.currentOrder.name] = this.currentOrder.id;

        if ((this.currentOrder.is_paid_with_cash() || this.currentOrder.get_change()) &&
            this.pos.config.iface_cashdrawer) {
            console.debug(`${DEBUG_TAG} Opening cash drawer`);
            this.hardwareProxy.printer.openCashbox();
        }

        if (isInvoiceRequested) {
            console.debug(`${DEBUG_TAG} Handling invoice request`);
            if (!orderJSON[0].raw.account_move) {
                console.error(`${DEBUG_TAG} No invoice generated`);
                this.dialog.add(AlertDialog, {
                    // title: _t("Invoice could not be generated"),
                    title: "Invoice could not be generated",
                    // body: _t("The invoice could not be generated."),
                    body: "The invoice could not be generated.",
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
            console.debug(`${DEBUG_TAG} Order finalized successfully`);
        } catch (error) {
            console.error(`${DEBUG_TAG} Failed to finalize order:`, error);
        }
        
        this.afterOrderValidation(true);
    },
});

