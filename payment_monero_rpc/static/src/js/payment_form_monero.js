/**
 * @module payment_form_monero
 * This module integrates Monero payments into Odoo's website checkout flow.
 */

/** @odoo-module **/

import publicWidget from '@web/legacy/js/public/public_widget';
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { loadJS } from "@web/core/assets";
import { rpc } from "@web/core/network/rpc";

const DEBUG_TAG = "[MoneroPayment]";

/**
 * @constant {string}
 * @memberof module:payment_form_monero
 */
const MONERO_PAYMENT_TEMPLATE = `
<div id="wrap">
    <div class="oe_website_sale o_website_sale_checkout container py-2">
        <div class="container mt-4 light-mode">
            <div class="row justify-content-center">
                <div class="col-md-12 text-center">
                    <h2>Pay with Monero</h2>
                    <div class="alert" id="payment_status_alert">
                        <h4><span id="payment_amount_str"></span> XMR</h4>
                    </div>
                    <div class="mb-4 border p-3">
                        <img id="qr_code_img" class="img-fluid" style="max-width: 250px" alt="Monero QR Code"/>
                    </div>
                    <div class="alert" id="payment_status_message">
                        <span id="status_message"></span>
                        <div id="status_check_container" style="display:none">
                            <a href="#" class="btn btn-sm btn-primary" id="check_status_btn">
                                Check Payment Status
                            </a>
                        </div>
                    </div>
                    <div class="text-left border-top pt-3">
                        <h5>How to Pay:</h5>
                        <ol>
                            <li>Open your Monero wallet</li>
                            <li>Send the exact amount to the address above</li>
                            <li>Wait for confirmations</li>
                        </ol>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
`;

/**
 * The Monero Payment Form widget integrates Monero payments into Odoo's checkout page.
 *
 * @class MoneroPaymentForm
 * @alias module:payment_form_monero.PaymentForm
 */
publicWidget.registry.PaymentForm = publicWidget.Widget.extend({

    /**
     * CSS selector for this widget.
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    selector: '#o_payment_form',

    events: {
        'click [name="o_payment_radio"]': '_onPaymentMethodSelected'
    },

    /**
     * Initialize the payment form widget.
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    init: function() {
        console.debug(`${DEBUG_TAG} Initializing payment form widget`);
        this._super.apply(this, arguments);
        this.moneroPaymentContainer = null;
        this.clipboard = null;
        this.statusCheckInterval = null;
        this.moneroSelected = false;
        this.currentPaymentId = null;
        this.submitButton = null;
        this._boundOnSubmitPayment = this._onSubmitPayment.bind(this);
    },

    /**
     * Load dependencies before widget starts.
     * @returns {Promise<void>}
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    willStart: async function() {
        return Promise.all([
            loadJS('/payment_monero_rpc/static/src/js/clipboard.min.js').catch(e => {
                console.error(`${DEBUG_TAG} Failed to load clipboard.js:`, e);
            }),
            this._super.apply(this, arguments)
        ]);
    },

    /**
     * Start the widget and set up event listeners.
     * @returns {Promise<void>}
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    start: function() {
        this.submitButton = document.querySelector('button[name="o_payment_submit_button"]');
        if (this.submitButton) {
            this.submitButton.addEventListener('click', this._boundOnSubmitPayment);
        }
        return this._super.apply(this, arguments).then(() => {
            this._handleInitialSelection();
        });
    },

    /**
     * Handle initial payment method selection on page load.
     * @private
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    _handleInitialSelection: function() {
        const selectedRadio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        if (selectedRadio) {
            this._onPaymentMethodSelected({ currentTarget: selectedRadio });
        }
    },

    /**
     * Handle payment method selection change.
     * @param {Event} ev
     * @private
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    _onPaymentMethodSelected: function(ev) {
        const providerCode = this._getProviderCode(ev.currentTarget);
        this.moneroSelected = (providerCode === 'monero_rpc');
        this._updatePayButtonText(this.moneroSelected ? _t("Pay with Monero") : _t("Pay Now"));
    },

    /**
     * Handle form submission for Monero payments.
     * @param {Event} ev
     * @returns {Promise<void>}
     * @private
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    _onSubmitPayment: async function(ev) {
        ev.preventDefault();
        ev.stopPropagation();

        if (!this.moneroSelected) {
            return this._super.apply(this, arguments);
        }

        try {
            this._disablePaymentForm();
            const checkedRadio = this.el.querySelector('input[name="o_payment_radio"]:checked');
            const paymentResponse = await this._processMoneroPayment(checkedRadio);

            if (paymentResponse.error) throw new Error(paymentResponse.error);
            if (!paymentResponse.payment_id) throw new Error("Invalid payment data received");

            const paymentData = paymentResponse.payment || {};
            paymentData.payment_id = paymentResponse.payment_id;
            await this._displayMoneroPaymentPage(paymentData);
        } catch (error) {
            this._displayError(_t("Payment Error"), error.message);
            this._enablePaymentForm();
        }
    },

    /**
     * Process Monero payment by making RPC call to the server.
     * @param {Element} radio
     * @returns {Promise<Object>}
     * @private
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    _processMoneroPayment: async function(radio) {
        const amountTotal = document.getElementById('amount_total_summary');
        if (!amountTotal) throw new Error("Missing order information");

        const orderId = amountTotal.getAttribute('data-oe-id') || amountTotal.dataset.oeId;
        if (!orderId || isNaN(parseInt(orderId))) throw new Error(_t("Missing or invalid order ID — cannot process payment"));

        const providerId = this._getProviderId(radio);
        const providerCode = this._getProviderCode(radio);

        // Issue 11: the server endpoint requires access_token for _validate_order_access.
        // Without it the server always raises AccessError and checkout silently fails.
        // The token is available in the page DOM in multiple standard Odoo locations.
        const accessToken = (
            document.querySelector('input[name="access_token"]')?.value ||
            document.querySelector('[data-access-token]')?.dataset.accessToken ||
            document.querySelector('.o_portal_wrap [data-token]')?.dataset.token ||
            ''
        );

        const endpoint = `/shop/payment/monero/process/${orderId}`;
        const response = await rpc(endpoint, {
            provider: providerId,
            provider_code: providerCode,
            order_sudo: parseInt(orderId),
            access_token: accessToken,   // required by server _validate_order_access
            csrf_token: odoo.csrf_token,
        }, { shadow: true, timeout: 30000 });

        if (!response || !response.payment_id) throw new Error("Invalid response format");
        this.currentPaymentId = response.payment_id;
        return response;
    },

    /**
     * Display the Monero payment page.
     * @param {Object} payment
     * @returns {Promise<void>}
     * @private
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    _displayMoneroPaymentPage: async function(payment) {
        this._cleanupPaymentContainer();

        this.moneroPaymentContainer = document.createElement('div');
        this.moneroPaymentContainer.id = 'monero_payment_container';
        this.moneroPaymentContainer.className = 'monero-payment-container';

        this.el.parentNode.insertBefore(this.moneroPaymentContainer, this.el.nextSibling);
        this.el.style.display = 'none';

        this.moneroPaymentContainer.innerHTML = MONERO_PAYMENT_TEMPLATE;
        this._populatePaymentData(payment);
        await this._setupEventListeners();

        if (payment.state === 'pending' || payment.state === 'paid_unconfirmed') {
            this._startStatusChecking(payment.payment_id, payment.state);
        }
    },

    /**
     * Populate payment data into UI elements.
     * @param {Object} payment
     * @private
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    _populatePaymentData: function(payment) {
        // Use querySelector within the container — these IDs exist in MONERO_PAYMENT_TEMPLATE
        const amountEl = this.moneroPaymentContainer.querySelector('#payment_amount_str');
        if (amountEl) amountEl.textContent = payment.amount_str || '';

        // Issue 107: seller_address and order_reference are not in MONERO_PAYMENT_TEMPLATE.
        // Populate them into the status alert which IS present, to avoid silent no-ops.
        const statusAlert = this.moneroPaymentContainer.querySelector('#payment_status_alert');
        if (statusAlert && payment.address_seller) {
            const addrLine = document.createElement('p');
            addrLine.className = 'monero-address text-break small mt-2';
            addrLine.textContent = payment.address_seller;
            statusAlert.appendChild(addrLine);
        }
        if (statusAlert && payment.order_ref) {
            const refLine = document.createElement('p');
            refLine.className = 'text-muted small';
            refLine.textContent = _t("Order: %s", payment.order_ref);
            statusAlert.appendChild(refLine);
        }
    },

    /**
     * Set up event listeners for the payment page.
     * @returns {Promise<void>}
     * @private
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    _setupEventListeners: async function() {
        const checkStatusBtn = this.moneroPaymentContainer.querySelector('#check_status_btn');
        if (checkStatusBtn) {
            checkStatusBtn.addEventListener('click', (ev) => {
                ev.preventDefault();
                this._manualCheckStatus();
            });
        }
    },

    /**
     * Start periodically checking payment status.
     * @param {string} paymentId
     * @private
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    _startStatusChecking: function(paymentId, paymentState) {
        this._stopStatusChecking();
        // Issue 109: derive interval from payment state, not CSS class presence
        // Issue 108: interval is cleared in destroy() / _cleanupPaymentContainer() for SPA nav;
        // hard browser navigation leaks are unavoidable without a service worker.
        const checkInterval = (paymentState === 'paid_unconfirmed') ? 30000 : 60000;
        this.statusCheckInterval = setInterval(
            () => this._checkPaymentStatus(paymentId),
            checkInterval
        );
    },

    /**
     * Stop checking payment status.
     * @private
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    _stopStatusChecking: function() {
        if (this.statusCheckInterval) {
            clearInterval(this.statusCheckInterval);
            this.statusCheckInterval = null;
        }
    },

    /**
     * Manually trigger a payment status check.
     * @private
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    _manualCheckStatus: function() {
        const paymentId = this.currentPaymentId;
        if (paymentId) this._checkPaymentStatus(paymentId);
    },

    /**
     * Check the payment status via RPC call.
     * @param {string} paymentId
     * @returns {Promise<void>}
     * @private
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    _checkPaymentStatus: async function(paymentId) {
        const status = await rpc("/shop/payment/monero/status/" + paymentId, {}, {
            shadow: true,
            timeout: 10000
        });

        if (status.status === 'confirmed' || status.confirmations >= (status.required_confirmations || status.remaining_confirmations || 2)) {
            this._updateStatusDisplay({
                status: 'confirmed',
                status_message: "Payment confirmed! Thank you for your purchase.",
                status_alert_class: "success",
                status_icon: "fa-check-circle"
            });
            this._stopStatusChecking();
        }
    },

    /**
     * Update the status display with new data.
     * @param {Object} status
     * @private
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    _updateStatusDisplay: function(status) {
        const statusMessageEl = this.moneroPaymentContainer.querySelector('#status_message');
        if (statusMessageEl) {
            statusMessageEl.textContent = status.status_message;
        }
    },

    /**
     * Clean up the payment container.
     * @private
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    _cleanupPaymentContainer: function() {
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
     * Update the pay button text.
     * @param {string} text
     * @private
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    _updatePayButtonText: function(text) {
        if (this.submitButton) this.submitButton.textContent = text;
    },

    /**
     * Disable the payment form.
     * @private
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    _disablePaymentForm: function() {
        if (this.submitButton) this.submitButton.disabled = true;
        this.el.querySelectorAll('input').forEach(el => el.disabled = true);
        this.call('ui', 'block');
    },

    /**
     * Enable the payment form.
     * @private
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    _enablePaymentForm: function() {
        if (this.submitButton) this.submitButton.disabled = false;
        this.el.querySelectorAll('input').forEach(el => el.disabled = false);
        this.call('ui', 'unblock');
    },

    /**
     * Display an error dialog.
     * @param {string} title
     * @param {string} message
     * @private
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    _displayError: function(title, message) {
        this.call('dialog', 'add', ConfirmationDialog, { 
            title: title,
            body: message,
            confirmLabel: _t("OK"),
        });
    },

    /**
     * Get the provider code from a radio button.
     * @param {Element} radio
     * @returns {string}
     * @private
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    _getProviderCode: function(radio) {
        return radio.dataset.providerCode;
    },

    /**
     * Get the provider ID from a radio button.
     * @param {Element} radio
     * @returns {number}
     * @private
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    _getProviderId: function(radio) {
        return parseInt(radio.dataset.providerId);
    },

    /**
     * Clean up when widget is destroyed.
     * @memberof module:payment_form_monero.MoneroPaymentForm
     */
    destroy: function() {
        if (this.submitButton) {
            this.submitButton.removeEventListener('click', this._boundOnSubmitPayment);
        }
        this._cleanupPaymentContainer();
        this._super.apply(this, arguments);
    }
});

/**
 * @exports payment_form_monero
 */
export default publicWidget.registry.PaymentForm;

