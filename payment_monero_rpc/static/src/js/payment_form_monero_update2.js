/** @odoo-module **/

//TODO this is the future OWL-3 incarnation still in progress

import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { loadJS } from "@web/core/assets";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";
import { renderToString } from "@web/core/utils/render";
import { markup } from "@odoo/owl";

const DEBUG_TAG = "[MoneroPayment]";

export const PaymentFormMonero = {
    dependencies: ['ui', 'dialog'],

    setup() {
        this.ui = useService('ui');
        this.dialog = useService('dialog');
        this.action = useService('action');
        this.orm = useService('orm');
    },

    /**
     * Initialize the payment form component
     */
    init() {
        console.debug(`${DEBUG_TAG} Initializing payment form widget`);
        this.moneroPaymentContainer = null;
        this.clipboard = null;
        this.statusCheckInterval = null;
        this.moneroSelected = false;
        this.currentPaymentId = null;
        this._boundOnSubmitPayment = this._onSubmitPayment.bind(this);
    },

    /**
     * Load dependencies before component starts
     */
    async willStart() {
        console.debug(`${DEBUG_TAG} Loading dependencies`);
        try {
            await loadJS('/payment_monero_rpc/static/src/js/clipboard.min.js');
        } catch (e) {
            console.error(`${DEBUG_TAG} Failed to load clipboard.js:`, e);
        }
    },

    /**
     * Start the component and set up initial state
     */
    start() {
        console.debug(`${DEBUG_TAG} Starting payment form widget`);
        this.submitButton = document.querySelector('button[name="o_payment_submit_button"]');
        if (this.submitButton) {
            console.debug(`${DEBUG_TAG} Found submit button, attaching handler`);
            this.submitButton.addEventListener('click', this._boundOnSubmitPayment);
        }
        this._handleInitialSelection();
    },

    /**
     * Handle the initial payment method selection
     */
    _handleInitialSelection() {
        const selectedRadio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        if (selectedRadio) {
            console.debug(`${DEBUG_TAG} Found default payment selection:`, selectedRadio.dataset.providerCode);
            this._onPaymentMethodSelected({ currentTarget: selectedRadio });
        }
    },

    /**
     * Handle payment method selection change
     * @param {Event} ev - The change event
     */
    _onPaymentMethodSelected(ev) {
        const providerCode = this._getProviderCode(ev.currentTarget);
        console.debug(`${DEBUG_TAG} Payment method changed to:`, providerCode);
        
        this.moneroSelected = (providerCode === 'monero_rpc');
        this._updatePayButtonText(
            this.moneroSelected ? _t("Pay with Monero") : _t("Pay Now")
        );
    },

    /**
     * Handle form submission
     * @param {Event} ev - The submit event
     */
    async _onSubmitPayment(ev) {
        console.debug(`${DEBUG_TAG} Form submission initiated`);
        ev.preventDefault();
        ev.stopPropagation();

        if (!this.moneroSelected) {
            console.debug(`${DEBUG_TAG} Non-Monero payment selected, using default flow`);
            return;
        }

        try {
            this._disablePaymentForm();
            const checkedRadio = this.el.querySelector('input[name="o_payment_radio"]:checked');
            const paymentResponse = await this._processMoneroPayment(checkedRadio);
            
            if (paymentResponse.error) {
                throw new Error(paymentResponse.error);
            }
            
            if (!paymentResponse || !paymentResponse.payment_id) {
                throw new Error("Invalid payment data received");
            }
            
            const paymentData = paymentResponse.payment || {};
            paymentData.payment_id = paymentResponse.payment_id;
            
            await this._displayMoneroPaymentPage(paymentData);
        } catch (error) {
            console.error(`${DEBUG_TAG} Payment processing failed:`, error);
            this._displayError(
                _t("Payment Error"),
                error.message || _t("Failed to process Monero payment. Please try again.")
            );
            this._enablePaymentForm();
        }
    },

    /**
     * Process Monero payment request
     * @param {HTMLElement} radio - The selected payment radio button
     * @returns {Promise<Object>} - The payment response
     */
    async _processMoneroPayment(radio) {
        console.debug(`${DEBUG_TAG} Creating Monero transaction request`);
        
        const amountTotal = document.getElementById('amount_total_summary');
        if (!amountTotal) {
            throw new Error("Missing order information");
        }
        
        const orderId = amountTotal.getAttribute('data-oe-id') || amountTotal.dataset.oeId;
        if (!orderId) {
            throw new Error("Missing order ID");
        }

        const providerId = this._getProviderId(radio);
        const providerCode = this._getProviderCode(radio);
        
        try {
            const endpoint = `/shop/payment/monero/process/${orderId}`;
            console.debug(`${DEBUG_TAG} Calling endpoint: ${endpoint}`);
            
            const response = await rpc(endpoint, {
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
                throw new Error("Empty response from server");
            }
            
            if (response.error) {
                throw new Error(response.error);
            }
            
            if (!response.payment_id) {
                throw new Error("Invalid response format - missing payment_id");
            }
            
            this.currentPaymentId = response.payment_id;
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
    },

    /**
     * Display the Monero payment page
     * @param {Object} payment - The payment data
     */
    async _displayMoneroPaymentPage(payment) {
        console.debug(`${DEBUG_TAG} Displaying Monero payment page`);
        this._cleanupPaymentContainer();

        this.moneroPaymentContainer = document.createElement('div');
        this.moneroPaymentContainer.id = 'monero_payment_container';
        this.el.parentNode.insertBefore(this.moneroPaymentContainer, this.el.nextSibling);
        this.el.style.display = 'none';

        // Render the static template (already loaded via assets)
        const templateContent = document.createElement('div');
        templateContent.innerHTML = renderToString('payment_monero_rpc.monero_payment_template_page', {
            payment_data: payment
        });
        console.debug(`${DEBUG_TAG} Rendering payment template`);

        // Append the rendered template
        this.moneroPaymentContainer.appendChild(templateContent);

        // Populate dynamic data & setup events
        this._populatePaymentData(payment);
        await this._setupEventListeners();

        if (payment.state === 'pending' || payment.state === 'paid_unconfirmed') {
            this._startStatusChecking(payment.payment_id);
        }
        this.ui.unblock();
    },
    /**
     * Populate payment data in the template
     * @param {Object} payment - The payment data
     */
    _populatePaymentData(payment) {
        const setTextContent = (id, value) => {
            const el = document.getElementById(id);
            if (el && value !== undefined) el.textContent = value;
        };

        const setDisplay = (id, show) => {
            const el = document.getElementById(id);
            if (el) el.style.display = show ? '' : 'none';
        };

        setTextContent('payment_amount_str', payment.amount_str);
        setTextContent('instructions_amount_str', payment.amount_str);
        setTextContent('seller_address', payment.address_seller);
        setTextContent('order_reference', payment.order_ref || 'N/A');
        setTextContent('required_confirmations', payment.required_confirmations || '10');
        setTextContent('instructions_required_confirmations', payment.required_confirmations || '10');
        setTextContent('confirmations', payment.confirmations || '0');
        
        if (payment.id) {
            const qrImg = document.getElementById('qr_code_img');
            if (qrImg) qrImg.src = `/shop/payment/monero/qr/${payment.id}`;
        }

        if (payment.payment_id) {
            setTextContent('payment_id', payment.payment_id);
            setDisplay('payment_id_row', true);
        }

        if (payment.original_amount_str && payment.original_currency) {
            setDisplay('original_amount_container', true);
            setTextContent('original_amount_str', payment.original_amount_str);
            setTextContent('original_currency', payment.original_currency);
            setDisplay('instructions_original_amount', true);
            setTextContent('instructions_original_amount_value', payment.original_amount_str);
            setTextContent('instructions_original_currency', payment.original_currency);
        }

        if (payment.exchange_rate_str && payment.original_currency) {
            setDisplay('exchange_rate_container', true);
            setTextContent('exchange_rate_str', payment.exchange_rate_str);
            setTextContent('exchange_rate_currency', payment.original_currency);
        }

        if (payment.expiry_time_str) {
            setTextContent('expiry_time_str', payment.expiry_time_str);
            setDisplay('expiry_time_row', true);
        }

        if (payment.confirmations + payment.required_confirmations < 10) {
            setDisplay('confirmations_waiting', true);
            setTextContent('confirmations_needed', payment.required_confirmations);
        }

        const statusAlertClass = payment.status_alert_class || 'info';
        const statusAlertEl = document.getElementById('payment_status_alert');
        const statusMessageEl = document.getElementById('payment_status_message');
        const statusIconEl = document.getElementById('status_icon');
        
        if (statusAlertEl) statusAlertEl.className = `alert alert-${statusAlertClass}`;
        if (statusMessageEl) statusMessageEl.className = `alert alert-${statusAlertClass}`;
        if (statusIconEl) statusIconEl.className = `fa ${payment.status_icon || 'fa-info-circle'}`;
        setTextContent('status_message', payment.status_message || '');

        setDisplay('status_check_container', payment.state === 'pending');
        setDisplay('payment_proof_btn', payment.state === 'confirmed');
        setDisplay('wallet_uri_container', !!payment.monero_uri);

        if (payment.monero_uri) {
            const walletUriBtn = document.getElementById('wallet_uri_btn');
            if (walletUriBtn) walletUriBtn.href = payment.monero_uri;
        }

        if (payment.invoice_ids && payment.invoice_ids.length > 0) {
            const container = document.getElementById('invoice_download_container');
            if (container) {
                container.innerHTML = '';
                
                const dropdown = document.createElement('div');
                dropdown.className = 'dropdown';
                
                const button = document.createElement('button');
                button.className = 'btn btn-outline-primary dropdown-toggle';
                button.type = 'button';
                button.id = 'invoiceDropdown';
                button.setAttribute('data-toggle', 'dropdown');
                button.setAttribute('aria-haspopup', 'true');
                button.setAttribute('aria-expanded', 'false');
                button.innerHTML = '<i class="fa fa-file-pdf"></i> Download Invoice';
                
                const menu = document.createElement('div');
                menu.className = 'dropdown-menu';
                menu.setAttribute('aria-labelledby', 'invoiceDropdown');
                
                payment.invoice_ids.forEach(invoice_id => {
                    const link = document.createElement('a');
                    link.className = 'dropdown-item';
                    link.href = `/my/invoices/${invoice_id}?download=1`;
                    link.textContent = `Invoice ${invoice_id}`;
                    menu.appendChild(link);
                });
                
                dropdown.appendChild(button);
                dropdown.appendChild(menu);
                container.appendChild(dropdown);
                
                const disabledBtn = container.querySelector('.disabled');
                if (disabledBtn) {
                    disabledBtn.remove();
                }
            }
        }
    },

    /**
     * Set up event listeners for the payment page
     */
    async _setupEventListeners() {
        const checkStatusBtn = this.moneroPaymentContainer.querySelector('#check_status_btn');
        if (checkStatusBtn) {
            checkStatusBtn.addEventListener('click', (ev) => {
                ev.preventDefault();
                console.debug(`${DEBUG_TAG} Manual status check triggered`);
                this._manualCheckStatus();
            });
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
        }
    },

    /**
     * Start periodic status checking
     * @param {string} paymentId - The payment ID to check
     */
    _startStatusChecking(paymentId) {
        console.debug(`${DEBUG_TAG} Configuring status check interval`);
        this._stopStatusChecking();
        
        const checkInterval = this.moneroPaymentContainer.querySelector('.alert-warning') ? 30000 : 60000;
        console.debug(`${DEBUG_TAG} Setting check interval to ${checkInterval}ms`);
        this.statusCheckInterval = setInterval(
            () => this._checkPaymentStatus(paymentId), 
            checkInterval
        );
    },

    /**
     * Stop periodic status checking
     */
    _stopStatusChecking() {
        if (this.statusCheckInterval) {
            console.debug(`${DEBUG_TAG} Stopping status checks`);
            clearInterval(this.statusCheckInterval);
            this.statusCheckInterval = null;
        }
    },

    /**
     * Manually trigger a status check
     */
    _manualCheckStatus() {
        const paymentId = this.currentPaymentId;
        if (paymentId) {
            console.debug(`${DEBUG_TAG} Manual status check for payment:`, paymentId);
            this._checkPaymentStatus(paymentId);
        }
    },

    /**
     * Check payment status
     * @param {string} paymentId - The payment ID to check
     */
    async _checkPaymentStatus(paymentId) {
        console.debug(`${DEBUG_TAG} Checking payment status for:`, paymentId);
        try {
            const status = await rpc("/shop/payment/monero/status/" + paymentId, {}, {
                shadow: true,
                timeout: 10000
            });

            console.debug(`${DEBUG_TAG} Status check response:`, status);
            
            if (status.status === 'confirmed' || status.confirmations >= 10) {
                console.debug(`${DEBUG_TAG} Payment confirmed, clearing cart and redirecting`);
                this._updateStatusDisplay({
                    status: 'confirmed',
                    status_message: "Payment confirmed! Thank you for your purchase.",
                    status_alert_class: "success",
                    status_icon: "fa-check-circle"
                });
                this._stopStatusChecking();

                try {
                    await rpc("/shop/cart/clear", {}, {
                        shadow: true,
                        timeout: 10000
                    });
                } catch (clearError) {
                    console.warn(`${DEBUG_TAG} Could not clear cart:`, clearError);
                }

                setTimeout(() => {
                    if (this.el.dataset.returnUrl) {
                        window.location.href = this.el.dataset.returnUrl;
                    }
                }, 1500);
                return;
            }
            
            if (status.error) {
                throw new Error(status.error);
            }
            
            if (status.status === 'paid_unconfirmed') {
                console.debug(`${DEBUG_TAG} Payment unconfirmed, updating display`);
                this._updateStatusDisplay({
                    ...status,
                    status_message: "Payment received - awaiting confirmation",
                    status_alert_class: "warning",
                    confirmation: "We've received your payment but it's awaiting network confirmation. This may take a few minutes."
                });
                this._startStatusChecking(paymentId);
            } else if (status.status === 'pending') {
                console.debug(`${DEBUG_TAG} Payment still pending`);
                this._updateStatusDisplay({
                    ...status,
                    status_message: "Payment pending - please complete the transaction",
                    status_alert_class: "info",
                    confirmation: "Your payment is currently pending. Please complete the transaction process."
                });
            } else if (status.status === 'expired') {
                console.debug(`${DEBUG_TAG} Payment expired`);
                this._updateStatusDisplay({
                    ...status,
                    status_message: "Payment expired - please restart the payment process",
                    status_alert_class: "danger",
                    confirmation: "The payment session has expired. Please initiate a new payment if you wish to complete your purchase."
                });
                this._stopStatusChecking();
            }

        } catch (error) {
            console.error(`${DEBUG_TAG} Status check failed:`, error);
            this._updateStatusDisplay({
                status_message: "Error checking payment status: " + error.message,
                status_alert_class: "danger"
            });
        }
    },

    /**
     * Update the status display
     * @param {Object} status - The status data to display
     */
    _updateStatusDisplay(status) {
        console.debug(`${DEBUG_TAG} Update screen data with - `, status);
        
        const setTextContent = (id, value) => {
            const el = this.moneroPaymentContainer.querySelector(`#${id}`);
            if (el && value !== undefined) el.textContent = value;
        };

        const setDisplay = (id, show) => {
            const el = this.moneroPaymentContainer.querySelector(`#${id}`);
            if (el) el.style.display = show ? '' : 'none';
        };

        if (status.confirmations !== undefined) {
            setTextContent('confirmations', status.confirmations);
        }
        
        if (status.required_confirmations) {
            setTextContent('required_confirmations', status.required_confirmations);
            setTextContent('instructions_required_confirmations', status.required_confirmations);
        }

        if (status.status_message) {
            setTextContent('status_message', status.status_message);
        }
        
        const statusIconEl = this.moneroPaymentContainer.querySelector('#status_icon');
        if (statusIconEl && status.status_icon_class) {
            statusIconEl.className = `fa ${status.status_icon_class}`;
        }

        const statusAlertEl = this.moneroPaymentContainer.querySelector('#payment_status_message');
        if (statusAlertEl && status.status_alert_class) {
            statusAlertEl.className = `alert alert-${status.status_alert_class}`;
        }

        setDisplay('status_check_container', !status.payment_complete);
        setDisplay('wallet_uri_container', !status.payment_complete);
    },
    
    /**
     * Clean up the payment container
     */
    _cleanupPaymentContainer() {
        console.debug(`${DEBUG_TAG} Cleaning up payment container`);
        this._stopStatusChecking();

        if (this.clipboard) {
            this.clipboard.destroy();
            this.clipboard = null;
        }

        if (this.moneroPaymentContainer) {
            this.moneroPaymentContainer.remove();
            this.moneroPaymentContainer = null;
        }

        this.el.style.display = '';
    },

    /**
     * Update the pay button text
     * @param {string} text - The new button text
     */
    _updatePayButtonText(text) {
        if (this.submitButton) {
            console.debug(`${DEBUG_TAG} Updating pay button text to:`, text);
            this.submitButton.textContent = text;
        }
    },

    /**
     * Disable the payment form
     */
    _disablePaymentForm() {
        console.debug(`${DEBUG_TAG} Disabling payment form`);
        if (this.submitButton) {
            this.submitButton.disabled = true;
        }
        this.el.querySelectorAll('input').forEach(el => el.disabled = true);
        this.ui.block();
    },

    /**
     * Enable the payment form
     */
    _enablePaymentForm() {
        console.debug(`${DEBUG_TAG} Enabling payment form`);
        if (this.submitButton) {
            this.submitButton.disabled = false;
        }
        this.el.querySelectorAll('input').forEach(el => el.disabled = false);
        this.ui.unblock();
    },

    /**
     * Display an error dialog
     * @param {string} title - The dialog title
     * @param {string} message - The error message
     */
    _displayError(title, message) {
        console.debug(`${DEBUG_TAG} Displaying error dialog:`, title, message);
        this.dialog.add(ConfirmationDialog, { 
            title: title, 
            body: markup(message),
            confirmLabel: _t("OK"),
        });
    },

    /**
     * Get the provider code from a radio button
     * @param {HTMLElement} radio - The radio button element
     * @returns {string} - The provider code
     */
    _getProviderCode(radio) {
        return radio.dataset.providerCode;
    },

    /**
     * Get the provider ID from a radio button
     * @param {HTMLElement} radio - The radio button element
     * @returns {number} - The provider ID
     */
    _getProviderId(radio) {
        return parseInt(radio.dataset.providerId);
    },

    /**
     * Clean up when component is destroyed
     */
    destroy() {
        console.debug(`${DEBUG_TAG} Destroying widget`);
        if (this.submitButton) {
            this.submitButton.removeEventListener('click', this._boundOnSubmitPayment);
        }
        this._cleanupPaymentContainer();
    }
};

// Patch the original PaymentForm with our Monero payment functionality
PaymentForm.include(PaymentFormMonero);
