/** @odoo-module **/

//TODO this is the future OWL-3 incarnation still in progress.

import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { renderToString } from "@web/core/utils/render";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { loadJS } from "@web/core/assets";
import publicWidget from '@web/legacy/js/public/public_widget';

const DEBUG_TAG = "[MoneroPayment]";

export class MoneroPaymentForm extends Component {
    static template = "payment_monero_rpc.MoneroPaymentForm";

    setup() {
        console.debug(`${DEBUG_TAG} Initializing component setup`);
        this.rpc = useService("rpc");
        this.dialog = useService("dialog");
        this.ui = useService("ui");
        this.state = useState({
            paymentData: null,
            currentPaymentId: null,
            moneroSelected: false,
            statusCheckInterval: null,
        });

        this.submitButton = null;
        this.clipboard = null;
        this.moneroPaymentContainer = null;

        console.debug(`${DEBUG_TAG} Setting up lifecycle hooks`);
        onMounted(() => {
            console.debug(`${DEBUG_TAG} Component mounted`);
            this.onMounted();
        });
        onWillUnmount(() => {
            console.debug(`${DEBUG_TAG} Component will unmount`);
            this.onWillUnmount();
        });
    }

    onMounted() {
        console.debug(`${DEBUG_TAG} Starting onMounted`);
        console.debug(`${DEBUG_TAG} Searching for submit button`);
        this.submitButton = document.querySelector('button[name="o_payment_submit_button"]');
        
        if (this.submitButton) {
            console.debug(`${DEBUG_TAG} Found submit button:`, this.submitButton);
            console.debug(`${DEBUG_TAG} Current button text:`, this.submitButton.textContent);
            console.debug(`${DEBUG_TAG} Adding click event listener`);
            this.submitButton.addEventListener("click", this.onSubmitPayment.bind(this));
        } else {
            console.error(`${DEBUG_TAG} Could not find submit button in DOM!`);
            console.debug(`${DEBUG_TAG} Available buttons:`, document.querySelectorAll('button'));
        }

        console.debug(`${DEBUG_TAG} Checking initial payment selection`);
        this.handleInitialSelection();
    }

    onWillUnmount() {
        console.debug(`${DEBUG_TAG} Starting onWillUnmount cleanup`);
        if (this.submitButton) {
            console.debug(`${DEBUG_TAG} Removing event listener from submit button`);
            this.submitButton.removeEventListener("click", this.onSubmitPayment.bind(this));
        }
        console.debug(`${DEBUG_TAG} Cleaning up payment container`);
        this.cleanupPaymentContainer();
    }

    handleInitialSelection() {
        console.debug(`${DEBUG_TAG} Checking for initially selected payment method`);
        const selectedRadio = document.querySelector('input[name="o_payment_radio"]:checked');
        
        if (selectedRadio) {
            console.debug(`${DEBUG_TAG} Found default selection:`, {
                providerCode: selectedRadio.dataset.providerCode,
                element: selectedRadio
            });
            this.onPaymentMethodSelected({ currentTarget: selectedRadio });
        } else {
            console.debug(`${DEBUG_TAG} No payment method selected by default`);
        }
    }

    onPaymentMethodSelected(ev) {
        if (!ev || !ev.currentTarget) {
            console.error(`${DEBUG_TAG} Invalid event object in onPaymentMethodSelected:`, ev);
            return;
        }

        const providerCode = this.getProviderCode(ev.currentTarget);
        console.debug(`${DEBUG_TAG} Payment method changed to:`, providerCode);
        
        this.state.moneroSelected = (providerCode === 'monero_rpc');
        console.debug(`${DEBUG_TAG} Monero selected state:`, this.state.moneroSelected);
        
        const newButtonText = this.state.moneroSelected ? _t("Pay with Monero") : _t("Pay Now");
        console.debug(`${DEBUG_TAG} Updating button text to:`, newButtonText);
        this.updatePayButtonText(newButtonText);
    }

    async onSubmitPayment(ev) {
        console.debug(`${DEBUG_TAG} Form submission initiated`);
        console.debug(`${DEBUG_TAG} Event details:`, {
            type: ev.type,
            target: ev.target,
            defaultPrevented: ev.defaultPrevented
        });

        ev.preventDefault();
        ev.stopPropagation();
        console.debug(`${DEBUG_TAG} Default form submission prevented`);

        if (!this.state.moneroSelected) {
            console.debug(`${DEBUG_TAG} Non-Monero payment selected, skipping Monero processing`);
            return;
        }

        try {
            console.debug(`${DEBUG_TAG} Starting Monero payment processing`);
            this.disablePaymentForm();
            
            console.debug(`${DEBUG_TAG} Looking for selected payment radio`);
            const checkedRadio = document.querySelector('input[name="o_payment_radio"]:checked');
            console.debug(`${DEBUG_TAG} Found radio:`, checkedRadio);

            console.debug(`${DEBUG_TAG} Processing Monero payment...`);
            const paymentResponse = await this.processMoneroPayment(checkedRadio);
            console.debug(`${DEBUG_TAG} Payment processing complete:`, paymentResponse);
            
            if (paymentResponse.error) {
                console.error(`${DEBUG_TAG} Payment error:`, paymentResponse.error);
                throw new Error(paymentResponse.error);
            }
            
            if (!paymentResponse || !paymentResponse.payment_id) {
                console.error(`${DEBUG_TAG} Invalid payment data:`, paymentResponse);
                throw new Error("Invalid payment data received");
            }
            
            const paymentData = paymentResponse.payment || {};
            paymentData.payment_id = paymentResponse.payment_id;
            this.state.paymentData = paymentData;
            this.state.currentPaymentId = paymentResponse.payment_id;
            console.debug(`${DEBUG_TAG} Updated component state with payment data`);
            
            console.debug(`${DEBUG_TAG} Displaying Monero payment page`);
            await this.displayMoneroPaymentPage(paymentData);
        } catch (error) {
            console.error(`${DEBUG_TAG} Payment processing failed:`, {
                error: error,
                message: error.message,
                stack: error.stack
            });
            this.displayError(
                _t("Payment Error"),
                error.message || _t("Failed to process Monero payment. Please try again.")
            );
            this.enablePaymentForm();
        }
    }

    async processMoneroPayment(radio) {
        console.debug(`${DEBUG_TAG} Starting Monero payment processing`);
        console.debug(`${DEBUG_TAG} Radio element:`, radio);

        const amountTotal = document.getElementById('amount_total_summary');
        if (!amountTotal) {
            console.error(`${DEBUG_TAG} Missing amount_total_summary element`);
            throw new Error("Missing order information");
        }
        
        const orderId = amountTotal.getAttribute('data-oe-id') || amountTotal.dataset.oeId;
        if (!orderId) {
            console.error(`${DEBUG_TAG} Missing order ID in amount_total_summary`);
            throw new Error("Missing order ID");
        }

        const providerId = this.getProviderId(radio);
        const providerCode = this.getProviderCode(radio);
        console.debug(`${DEBUG_TAG} Payment details:`, {
            providerId,
            providerCode,
            orderId
        });
        
        try {
            const endpoint = `/shop/payment/monero/process/${orderId}`;
            console.debug(`${DEBUG_TAG} Calling endpoint: ${endpoint}`);
            
            const response = await this.rpc(endpoint, {
                provider: providerId,
                provider_code: providerCode,
                order_sudo: parseInt(orderId),
                csrf_token: odoo.csrf_token,
            }, {
                shadow: true,
                timeout: 30000
            });
            
            console.debug(`${DEBUG_TAG} Received response:`, response);

            if (!response) {
                console.error(`${DEBUG_TAG} Empty response from server`);
                throw new Error("Empty response from server");
            }
            
            if (response.error) {
                console.error(`${DEBUG_TAG} Server returned error:`, response.error);
                throw new Error(response.error);
            }
            
            if (!response.payment_id) {
                console.error(`${DEBUG_TAG} Missing payment_id in response`);
                throw new Error("Invalid response format - missing payment_id");
            }
            
            this.state.currentPaymentId = response.payment_id;
            console.debug(`${DEBUG_TAG} Set currentPaymentId:`, this.state.currentPaymentId);
            return response;
        } catch (error) {
            console.error(`${DEBUG_TAG} RPC call failed:`, {
                error: error,
                message: error.message,
                stack: error.stack,
                data: error.data || null
            });
            
            throw new Error("Payment processing failed. Please try again or contact support.");
        }
    }

    async displayMoneroPaymentPage(payment) {
        console.debug(`${DEBUG_TAG} Displaying Monero payment page`);
        console.debug(`${DEBUG_TAG} Payment data:`, payment);
        this.cleanupPaymentContainer();

        this.moneroPaymentContainer = document.createElement('div');
        this.moneroPaymentContainer.id = 'monero_payment_container';
        this.moneroPaymentContainer.className = 'monero-payment-container';
        console.debug(`${DEBUG_TAG} Created payment container:`, this.moneroPaymentContainer);
        
        const paymentForm = document.querySelector('#o_payment_form');
        if (!paymentForm) {
            console.error(`${DEBUG_TAG} Could not find payment form`);
            throw new Error("Payment form not found");
        }

        paymentForm.parentNode.insertBefore(
            this.moneroPaymentContainer, 
            paymentForm.nextSibling
        );
        paymentForm.style.display = 'none';
        console.debug(`${DEBUG_TAG} Updated DOM with payment container`);

        try {
            console.debug(`${DEBUG_TAG} Rendering payment template`);
            const html = renderToString('payment_monero_rpc.monero_payment_template_page', {
                payment_data: payment
            });
            
            this.moneroPaymentContainer.innerHTML = html;
            console.debug(`${DEBUG_TAG} Template rendered successfully`);
            
            await this.setupEventListeners();
            console.debug(`${DEBUG_TAG} Event listeners setup complete`);

            if (payment.state === 'pending' || payment.state === 'paid_unconfirmed') {
                console.debug(`${DEBUG_TAG} Starting status checks for payment state:`, payment.state);
                this.startStatusChecking(payment.payment_id);
            }

            if (payment.state === 'pending') {
                console.debug(`${DEBUG_TAG} Adding refresh script for pending payment`);
                const refreshScript = document.createElement('script');
                refreshScript.textContent = `
                    setTimeout(function(){
                        console.debug('${DEBUG_TAG} Running payment refresh check');
                        const form = document.querySelector('#o_payment_form');
                        if (form) {
                            const moneroRadio = form.querySelector('input[data-provider-code="monero_rpc"]');
                            if (moneroRadio) {
                                moneroRadio.checked = true;
                                const payButton = form.querySelector('button[name="o_payment_submit_button"]');
                                if (payButton) {
                                    payButton.click();
                                }
                            }
                        }
                    }, 30000);
                `;
                this.moneroPaymentContainer.appendChild(refreshScript);
            }

            this.ui.unblock();
            console.debug(`${DEBUG_TAG} UI unblocked after payment page display`);
        } catch (error) {
            console.error(`${DEBUG_TAG} Failed to display payment page:`, {
                error: error,
                message: error.message,
                stack: error.stack
            });
            this.ui.unblock();
            throw new Error("Failed to display payment page. Please try again.");
        }
    }

    async setupEventListeners() {
        console.debug(`${DEBUG_TAG} Setting up event listeners`);
        
        const checkStatusBtn = this.moneroPaymentContainer.querySelector('#check_status_btn');
        if (checkStatusBtn) {
            console.debug(`${DEBUG_TAG} Found check status button`);
            checkStatusBtn.addEventListener('click', (ev) => {
                ev.preventDefault();
                console.debug(`${DEBUG_TAG} Manual status check triggered`);
                this.manualCheckStatus();
            });
        } else {
            console.debug(`${DEBUG_TAG} No check status button found`);
        }

        if (typeof ClipboardJS !== 'undefined') {
            console.debug(`${DEBUG_TAG} Initializing clipboard`);
            this.clipboard = new ClipboardJS('.copy-btn');
            this.clipboard.on('success', (e) => {
                console.debug(`${DEBUG_TAG} Copied to clipboard:`, e.text);
                const btn = e.trigger;
                btn.setAttribute('title', _t("Copied!"));
                const icon = btn.querySelector('i');
                if (icon) icon.className = 'fa fa-check';
                setTimeout(() => {
                    btn.setAttribute('title', _t("Copy to clipboard"));
                    if (icon) icon.className = 'fa fa-copy';
                }, 2000);
            });
        } else {
            console.debug(`${DEBUG_TAG} ClipboardJS not available`);
        }
    }

    startStatusChecking(paymentId) {
        console.debug(`${DEBUG_TAG} Starting status checking for payment:`, paymentId);
        this.stopStatusChecking();
        
        const checkInterval = this.moneroPaymentContainer.querySelector('.alert-warning') ? 30000 : 60000;
        console.debug(`${DEBUG_TAG} Setting check interval to ${checkInterval}ms`);
        
        this.state.statusCheckInterval = setInterval(() => {
            console.debug(`${DEBUG_TAG} Running automatic status check`);
            this.checkPaymentStatus(paymentId);
        }, checkInterval);
    }

    stopStatusChecking() {
        if (this.state.statusCheckInterval) {
            console.debug(`${DEBUG_TAG} Stopping status checks`);
            clearInterval(this.state.statusCheckInterval);
            this.state.statusCheckInterval = null;
        } else {
            console.debug(`${DEBUG_TAG} No active status check interval to stop`);
        }
    }

    manualCheckStatus() {
        const paymentId = this.state.currentPaymentId;
        if (paymentId) {
            console.debug(`${DEBUG_TAG} Manual status check for payment:`, paymentId);
            this.checkPaymentStatus(paymentId);
        } else {
            console.debug(`${DEBUG_TAG} No currentPaymentId for manual check`);
        }
    }

    async checkPaymentStatus(paymentId) {
        console.debug(`${DEBUG_TAG} Checking payment status for:`, paymentId);
        try {
            const status = await this.rpc("/shop/payment/monero/status/" + paymentId, {}, {
                shadow: true,
                timeout: 10000
            });

            console.debug(`${DEBUG_TAG} Status check response:`, status);
            
            if (status.status === 'confirmed' || status.confirmations >= 10) {
                console.debug(`${DEBUG_TAG} Payment confirmed, clearing cart and redirecting`);
                status.status = 'confirmed';
                this._updateStatusDisplay({
                    ...status,
                    status_message: "Payment confirmed! Thank you for your purchase.",
                    status_alert_class: "success",
                    status_icon: "fa-check-circle"
                });
                this.stopStatusChecking();

                try {
                    // Clear the cart. Better though should select actual concerned cart item and remove
                    //TODO Remove actual cart item
                    await this.rpc("/shop/cart/clear", {}, {
                        shadow: true,
                        timeout: 10000
                    });
                } catch (clearError) {
                    console.warn(`${DEBUG_TAG} Could not clear cart:`, clearError);
                }

                // Redirect after a short delay to allow UI updates
                setTimeout(() => {
                    const form = document.querySelector('#o_payment_form');
                    if (form && form.dataset.returnUrl) {
                        window.location.href = form.dataset.returnUrl;
                    }
                }, 1500);
                return;
            }
            
            if (status.error) {
                console.error(`${DEBUG_TAG} Status check error:`, status.error);
                throw new Error(status.error);
            }
            
            if (status.status === 'paid_unconfirmed') {
                console.debug(`${DEBUG_TAG} Payment received but unconfirmed`);
                this.updateStatusDisplay({
                    ...status,
                    status_message: "Payment received - awaiting confirmation",
                    status_alert_class: "warning",
                    confirmation: "We've received your payment but it's awaiting network confirmation. This may take a few minutes."
                });
                this.startStatusChecking(paymentId);
            } else if (status.status === 'pending') {
                console.debug(`${DEBUG_TAG} Payment still pending`);
                this.updateStatusDisplay({
                    ...status,
                    status_message: "Payment pending - please complete the transaction",
                    status_alert_class: "info",
                    confirmation: "Your payment is currently pending. Please complete the transaction process."
                });
            } else if (status.status === 'expired') {
                console.debug(`${DEBUG_TAG} Payment expired`);
                this.updateStatusDisplay({
                    ...status,
                    status_message: "Payment expired - please restart the payment process",
                    status_alert_class: "danger",
                    confirmation: "The payment session has expired. Please initiate a new payment if you wish to complete your purchase."
                });
                this.stopStatusChecking();
            }

        } catch (error) {
            console.error(`${DEBUG_TAG} Status check failed:`, {
                error: error,
                message: error.message,
                stack: error.stack
            });
            this.updateStatusDisplay({
                status_message: "Error checking payment status: " + error.message,
                status_alert_class: "danger"
            });
        }
    }

    updateStatusDisplay(status) {
        console.debug(`${DEBUG_TAG} Updating status display with:`, status);
        
        if (!this.moneroPaymentContainer) {
            console.debug(`${DEBUG_TAG} No payment container available for update`);
            return;
        }

        const confirmationsEl = this.moneroPaymentContainer.querySelector('#confirmations');
        const requiredConfirmationsEl = this.moneroPaymentContainer.querySelector('#required_confirmations');
        const statusMessageEl = this.moneroPaymentContainer.querySelector('#status_message');
        const statusIconEl = this.moneroPaymentContainer.querySelector('#status_icon');
        const statusAlertEl = this.moneroPaymentContainer.querySelector('#payment_status_message');
        const checkStatusBtn = this.moneroPaymentContainer.querySelector('#check_status_btn');
        const walletUriContainer = this.moneroPaymentContainer.querySelector('#wallet_uri_container');

        if (confirmationsEl && status.confirmations !== undefined) {
            console.debug(`${DEBUG_TAG} Updating confirmations:`, status.confirmations);
            confirmationsEl.textContent = status.confirmations;
        }
        
        if (requiredConfirmationsEl && status.required_confirmations) {
            console.debug(`${DEBUG_TAG} Updating required confirmations:`, status.required_confirmations);
            requiredConfirmationsEl.textContent = status.required_confirmations;
        }

        if (statusMessageEl && status.status_message) {
            console.debug(`${DEBUG_TAG} Updating status message:`, status.status_message);
            statusMessageEl.textContent = status.status_message;
        }
        
        if (statusIconEl && status.status_icon_class) {
            console.debug(`${DEBUG_TAG} Updating status icon:`, status.status_icon_class);
            statusIconEl.className = `fa ${status.status_icon_class}`;
        }

        if (statusAlertEl && status.status_alert_class) {
            console.debug(`${DEBUG_TAG} Updating alert class:`, status.status_alert_class);
            statusAlertEl.className = `alert alert-${status.status_alert_class}`;
        }

        if (checkStatusBtn && status.payment_complete) {
            console.debug(`${DEBUG_TAG} Hiding check status button`);
            checkStatusBtn.style.display = 'none';
        }
        
        if (walletUriContainer && status.payment_complete) {
            console.debug(`${DEBUG_TAG} Hiding wallet URI container`);
            walletUriContainer.style.display = 'none';
        }
    }
    
    cleanupPaymentContainer() {
        console.debug(`${DEBUG_TAG} Cleaning up payment container`);
        this.stopStatusChecking();

        if (this.clipboard) {
            console.debug(`${DEBUG_TAG} Destroying clipboard instance`);
            this.clipboard.destroy();
            this.clipboard = null;
        }

        if (this.moneroPaymentContainer) {
            console.debug(`${DEBUG_TAG} Removing payment container from DOM`);
            this.moneroPaymentContainer.remove();
            this.moneroPaymentContainer = null;
        }

        const paymentForm = document.querySelector('#o_payment_form');
        if (paymentForm) {
            console.debug(`${DEBUG_TAG} Restoring payment form visibility`);
            paymentForm.style.display = '';
        }
    }

    updatePayButtonText(text) {
        console.debug(`${DEBUG_TAG} Attempting to update button text to: '${text}'`);
        
        if (!this.submitButton) {
            console.warn(`${DEBUG_TAG} No submitButton reference, re-querying DOM`);
            this.submitButton = document.querySelector('button[name="o_payment_submit_button"]');
            
            if (!this.submitButton) {
                console.error(`${DEBUG_TAG} Could not find submit button in DOM!`);
                return;
            }
        }

        console.debug(`${DEBUG_TAG} Current button text: '${this.submitButton.textContent}'`);
        this.submitButton.textContent = text;
        console.debug(`${DEBUG_TAG} Button text updated to: '${this.submitButton.textContent}'`);
        
        // Verify the change was applied
        setTimeout(() => {
            const currentText = document.querySelector('button[name="o_payment_submit_button"]')?.textContent;
            console.debug(`${DEBUG_TAG} DOM verification - current button text: '${currentText}'`);
        }, 100);
    }

    disablePaymentForm() {
        console.debug(`${DEBUG_TAG} Disabling payment form`);
        if (this.submitButton) {
            console.debug(`${DEBUG_TAG} Disabling submit button`);
            this.submitButton.disabled = true;
        }
        
        const inputs = document.querySelectorAll('#o_payment_form input');
        console.debug(`${DEBUG_TAG} Disabling ${inputs.length} form inputs`);
        inputs.forEach(el => el.disabled = true);
        
        console.debug(`${DEBUG_TAG} Blocking UI`);
        this.ui.block();
    }

    enablePaymentForm() {
        console.debug(`${DEBUG_TAG} Enabling payment form`);
        if (this.submitButton) {
            console.debug(`${DEBUG_TAG} Enabling submit button`);
            this.submitButton.disabled = false;
        }
        
        const inputs = document.querySelectorAll('#o_payment_form input');
        console.debug(`${DEBUG_TAG} Enabling ${inputs.length} form inputs`);
        inputs.forEach(el => el.disabled = false);
        
        console.debug(`${DEBUG_TAG} Unblocking UI`);
        this.ui.unblock();
    }

    displayError(title, message) {
        console.debug(`${DEBUG_TAG} Displaying error dialog:`, {
            title: title,
            message: message
        });
        this.dialog.add(ConfirmationDialog, { 
            title: title, 
            body: message,
            confirmLabel: _t("OK"),
        });
    }

    getProviderCode(radio) {
        const code = radio.dataset.providerCode;
        console.debug(`${DEBUG_TAG} Getting provider code:`, code);
        return code;
    }

    getProviderId(radio) {
        const id = parseInt(radio.dataset.providerId);
        console.debug(`${DEBUG_TAG} Getting provider ID:`, id);
        return id;
    }
}

export default MoneroPaymentForm;
publicWidget.registry.PaymentForm = MoneroPaymentForm;
