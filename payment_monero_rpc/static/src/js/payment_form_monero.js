/** @odoo-module **/

//After payment succeeds, remember to remove sale from shopping cart
import publicWidget from '@web/legacy/js/public/public_widget';
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { loadJS } from "@web/core/assets";
import { rpc } from "@web/core/network/rpc";

const DEBUG_TAG = "[MoneroPayment]";

//TODO This is not a OWL-3 solution. MONERO_PAYMENT_TEMPLATE will be removed in the OWL-3 solution and replaced with a call to the
//     actual QWEB template.
const MONERO_PAYMENT_TEMPLATE = `
<div id="wrap">
    <div class="oe_website_sale o_website_sale_checkout container py-2">
        <div class="container mt-4 light-mode">
            <div class="row justify-content-center">
                <div class="col-md-12 text-center">
                    <h2>Pay with Monero</h2>

                    <div class="alert" id="payment_status_alert">
                        <h4>
                            <span id="payment_amount_str"></span> XMR
                            <div id="original_amount_container" style="display:none">
                                <br/>
                                <small>
                                    (≈ <span id="original_currency"></span> 
                                    <span id="original_amount_str"></span>)
                                </small>
                            </div>
                        </h4>
                        <small id="exchange_rate_container" style="display:none">
                            Rate: 1 XMR = 
                            <span id="exchange_rate_str"></span> 
                            <span id="exchange_rate_currency"></span>
                        </small>
                    </div>

                    <div class="mb-4 border p-3" style="background:white;display:inline-block">
                        <img id="qr_code_img" class="img-fluid" style="max-width: 250px" alt="Monero Payment QR Code"/>
                        <p class="mt-2 mb-0">
                            <i class="fa fa-qrcode"></i> 
                            Scan with Monero wallet
                        </p>
                    </div>

                    <div class="mb-3" id="invoice_download_container">
                        <a href="#" class="btn btn-outline-primary disabled">
                            <i class="fa fa-file-pdf"></i> No Invoices Available
                        </a>
                        <a href="#" class="btn btn-outline-secondary ml-2" id="payment_proof_btn" style="display:none">
                            <i class="fa fa-file-alt"></i> Payment Proof
                        </a>
                    </div>

                    <div class="card mb-4 text-left">
                        <div class="card-body">
                            <h5 class="card-title">Payment Details</h5>
                            <table class="table table-sm">
                                <tbody>
                                    <tr>
                                        <th>Seller Address:</th>
                                        <td class="monospace" style="word-break:break-all">
                                            <small id="seller_address"></small>
                                        </td>
                                    </tr>
                                    <tr id="payment_id_row" style="display:none">
                                        <th>Payment ID:</th>
                                        <td class="monospace"><small id="payment_id"></small></td>
                                    </tr>
                                    <tr>
                                        <th>Order Reference:</th>
                                        <td id="order_reference">N/A</td>
                                    </tr>
                                    <tr id="expiry_time_row" style="display:none">
                                        <th>Expires:</th>
                                        <td>
                                            <span id="expiry_time_str"></span>
                                        </td>
                                    </tr>
                                    <tr>
                                        <th>Confirmations:</th>
                                        <td>
                                            <span id="confirmations">0</span> remaining <span id="required_confirmations">2</span>
                                            <div id="confirmations_waiting" style="display:none">
                                                <br/>
                                                <small class="text-muted">
                                                    (Waiting for <span id="confirmations_needed">2</span> more)
                                                </small>
                                            </div>
                                        </td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <div class="alert" id="payment_status_message">
                        <i class="fa" id="status_icon"></i> 
                        <span id="status_message"></span>
                        <div id="status_check_container" style="display:none" class="mt-2">
                            <a href="#" class="btn btn-sm btn-primary" id="check_status_btn">
                                Check Payment Status
                            </a>
                        </div>
                    </div>

                    <div class="text-left border-top pt-3">
                        <h5>How to Pay:</h5>
                        <ol>
                            <li>Open your Monero wallet (GUI, CLI, or mobile)</li>
                            <li>
                                Send <strong id="instructions_amount_str"></strong> XMR to the address above
                                <div id="instructions_original_amount" style="display:none">
                                    (≈ <span id="instructions_original_currency"></span> 
                                    <span id="instructions_original_amount_value"></span>)
                                </div>
                            </li>
                            <li>Wait for <span id="instructions_required_confirmations">2</span> network confirmations</li>
                        </ol>
                        <p class="mt-2" id="wallet_uri_container" style="display:none">
                            <a href="#" class="btn btn-sm btn-outline-primary" id="wallet_uri_btn">
                                <i class="fa fa-external-link-alt"></i> Open in Wallet
                            </a>
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
`;

publicWidget.registry.PaymentForm = publicWidget.Widget.extend({
    selector: '#o_payment_form',
    events: {
        'click [name="o_payment_radio"]': '_onPaymentMethodSelected'
    },

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

    willStart: async function() {
        console.debug(`${DEBUG_TAG} Loading dependencies`);
        return Promise.all([
            loadJS('/payment_monero_rpc/static/src/js/clipboard.min.js').catch(e => {
                console.error(`${DEBUG_TAG} Failed to load clipboard.js:`, e);
            }),
            this._super.apply(this, arguments)
        ]);
    },

    start: function() {
        console.debug(`${DEBUG_TAG} Starting payment form widget`);
        
        this.submitButton = document.querySelector('button[name="o_payment_submit_button"]');
        if (this.submitButton) {
            console.debug(`${DEBUG_TAG} Found submit button, attaching handler`);
            this.submitButton.addEventListener('click', this._boundOnSubmitPayment);
        }
        
        return this._super.apply(this, arguments).then(() => {
            this._handleInitialSelection();
        });
    },

    _handleInitialSelection: function() {
        const selectedRadio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        if (selectedRadio) {
            console.debug(`${DEBUG_TAG} Found default payment selection:`, selectedRadio.dataset.providerCode);
            this._onPaymentMethodSelected({ currentTarget: selectedRadio });
        }
    },

    _onPaymentMethodSelected: function(ev) {
        const providerCode = this._getProviderCode(ev.currentTarget);
        console.debug(`${DEBUG_TAG} Payment method changed to:`, providerCode);
        
        this.moneroSelected = (providerCode === 'monero_rpc');
        this._updatePayButtonText(
            this.moneroSelected ? _t("Pay with Monero") : _t("Pay Now")
        );
    },

    _onSubmitPayment: async function(ev) {
        console.debug(`${DEBUG_TAG} Form submission initiated`);
        ev.preventDefault();
        ev.stopPropagation();

        if (!this.moneroSelected) {
            console.debug(`${DEBUG_TAG} Non-Monero payment selected, using default flow`);
            return this._super.apply(this, arguments);
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

    _processMoneroPayment: async function(radio) {
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

    _displayMoneroPaymentPage: async function(payment) {
        console.debug(`${DEBUG_TAG} Displaying Monero payment page`);
        this._cleanupPaymentContainer();

        this.moneroPaymentContainer = document.createElement('div');
        this.moneroPaymentContainer.id = 'monero_payment_container';
        this.moneroPaymentContainer.className = 'monero-payment-container';
        
        this.el.parentNode.insertBefore(this.moneroPaymentContainer, this.el.nextSibling);
        this.el.style.display = 'none';

        try {
            this.moneroPaymentContainer.innerHTML = MONERO_PAYMENT_TEMPLATE;
            this._populatePaymentData(payment);
            await this._setupEventListeners();

            if (payment.state === 'pending' || payment.state === 'paid_unconfirmed') {
                this._startStatusChecking(payment.payment_id);
            }

            if (payment.state === 'pending') {
                const refreshScript = document.createElement('script');
                refreshScript.textContent = `
                    setTimeout(function(){
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

            this.call('ui', 'unblock');
        } catch (error) {
            console.error(`${DEBUG_TAG} Failed to display payment page:`, error);
            this.call('ui', 'unblock');
            throw new Error("Failed to display payment page. Please try again.");
        }
    },

    _populatePaymentData: function(payment) {
        document.getElementById('payment_amount_str').textContent = payment.amount_str || '';
        document.getElementById('instructions_amount_str').textContent = payment.amount_str || '';
        document.getElementById('seller_address').textContent = payment.address_seller || '';
        document.getElementById('order_reference').textContent = payment.order_ref || 'N/A';
        document.getElementById('required_confirmations').textContent = payment.required_confirmations || '2';
        document.getElementById('instructions_required_confirmations').textContent = payment?.required_confirmations || '2';
        document.getElementById('confirmations').textContent = payment.confirmations || '0';
        
        if (payment.id) {
            document.getElementById('qr_code_img').src = `/shop/payment/monero/qr/${payment.id}`;
        }

        if (payment.payment_id) {
            document.getElementById('payment_id').textContent = payment.payment_id;
            document.getElementById('payment_id_row').style.display = '';
        }

        if (payment.original_amount_str && payment.original_currency) {
            document.getElementById('original_amount_container').style.display = '';
            document.getElementById('original_amount_str').textContent = payment.original_amount_str;
            document.getElementById('original_currency').textContent = payment.original_currency;
            document.getElementById('instructions_original_amount').style.display = '';
            document.getElementById('instructions_original_amount_value').textContent = payment.original_amount_str;
            document.getElementById('instructions_original_currency').textContent = payment.original_currency;
        }

        if (payment.exchange_rate_str && payment.original_currency) {
            document.getElementById('exchange_rate_container').style.display = '';
            document.getElementById('exchange_rate_str').textContent = payment.exchange_rate_str;
            document.getElementById('exchange_rate_currency').textContent = payment.original_currency;
        }

        if (payment.expiry_time_str) {
            document.getElementById('expiry_time_str').textContent = payment.expiry_time_str;
            document.getElementById('expiry_time_row').style.display = '';
        }

        if (payment.confirmations + payment.required_confirmations < 2) {
            document.getElementById('confirmations_waiting').style.display = '';
            document.getElementById('confirmations_needed').textContent = 
                payment.required_confirmations;
        }

        const statusAlertClass = payment.status_alert_class || 'info';
        document.getElementById('payment_status_alert').className = `alert alert-${statusAlertClass}`;
        document.getElementById('payment_status_message').className = `alert alert-${statusAlertClass}`;
        document.getElementById('status_icon').className = `fa ${payment.status_icon || 'fa-info-circle'}`;
        document.getElementById('status_message').textContent = payment.status_message || '';

        if (payment.state === 'pending') {
            document.getElementById('status_check_container').style.display = '';
        }

        if (payment.state === 'confirmed') {
            document.getElementById('payment_proof_btn').style.display = '';
        }

        if (payment.monero_uri) {
            document.getElementById('wallet_uri_container').style.display = '';
            document.getElementById('wallet_uri_btn').href = payment.monero_uri;
        }

        if (payment.invoice_ids && payment.invoice_ids.length > 0) {
            const container = document.getElementById('invoice_download_container');
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
    },

    _setupEventListeners: async function() {
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

    _startStatusChecking: function(paymentId) {
        console.debug(`${DEBUG_TAG} Configuring status check interval`);
        this._stopStatusChecking();
        
        const checkInterval = this.moneroPaymentContainer.querySelector('.alert-warning') ? 30000 : 60000;
        console.debug(`${DEBUG_TAG} Setting check interval to ${checkInterval}ms`);
        this.statusCheckInterval = setInterval(
            () => this._checkPaymentStatus(paymentId), 
            checkInterval
        );
    },

    _stopStatusChecking: function() {
        if (this.statusCheckInterval) {
            console.debug(`${DEBUG_TAG} Stopping status checks`);
            clearInterval(this.statusCheckInterval);
            this.statusCheckInterval = null;
        }
    },

    _manualCheckStatus: function() {
        const paymentId = this.currentPaymentId;
        if (paymentId) {
            console.debug(`${DEBUG_TAG} Manual status check for payment:`, paymentId);
            this._checkPaymentStatus(paymentId);
        }
    },

    _checkPaymentStatus: async function(paymentId) {
        console.debug(`${DEBUG_TAG} Checking payment status for:`, paymentId);
        try {
            const status = await rpc("/shop/payment/monero/status/" + paymentId, {
                // No need for additional params since payment_id is in the URL
            }, {
                shadow: true,
                timeout: 10000
            });

            console.debug(`${DEBUG_TAG} Status check response:`, status);
            
            // Force status to 'confirmed' in case it is not in sync with confirmations count
            if (status.status === 'confirmed' || status.confirmations >= 2) {
                console.debug(`${DEBUG_TAG} Payment confirmed, clearing cart and redirecting`);
                this._updateStatusDisplay({
                    status: 'confirmed',
                    status_message: "Payment confirmed! Thank you for your purchase.",
                    status_alert_class: "success",
                    status_icon: "fa-check-circle"
                });
                this._stopStatusChecking();

                try {
                    // Clear the cart
                    await rpc("/shop/cart/clear", {}, {
                        shadow: true,
                        timeout: 10000
                    });
                } catch (clearError) {
                    console.warn(`${DEBUG_TAG} Could not clear cart:`, clearError);
                }

                // Redirect after a short delay to allow UI updates
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

    _updateStatusDisplay: function(status) {
        console.debug(`${DEBUG_TAG} Update screen data with - `, status);
        
        // Update elements that might be in the template
        const confirmationsEl = this.moneroPaymentContainer.querySelector('#confirmations');
        const requiredConfirmationsEl = this.moneroPaymentContainer.querySelector('#required_confirmations');
        const requiredConfirmationsEl2 = this.moneroPaymentContainer.querySelector('#instructions_required_confirmations');
        const statusMessageEl = this.moneroPaymentContainer.querySelector('#status_message');
        const statusIconEl = this.moneroPaymentContainer.querySelector('#status_icon');
        const statusAlertEl = this.moneroPaymentContainer.querySelector('#payment_status_message');
        const checkStatusBtn = this.moneroPaymentContainer.querySelector('#check_status_btn');
        const walletUriContainer = this.moneroPaymentContainer.querySelector('#wallet_uri_container');

        if (confirmationsEl && status.confirmations !== undefined) {
            confirmationsEl.textContent = status.confirmations;
        }
        
        if (requiredConfirmationsEl && status.required_confirmations) {
            requiredConfirmationsEl.textContent = status.required_confirmations;
            requiredConfirmationsEl2.textContent = status.required_confirmations;
        }

        if (statusMessageEl && status.status_message) {
            statusMessageEl.textContent = status.status_message;
        }
        
        if (statusIconEl && status.status_icon_class) {
            statusIconEl.className = `fa ${status.status_icon_class}`;
        }

        if (statusAlertEl && status.status_alert_class) {
            statusAlertEl.className = `alert alert-${status.status_alert_class}`;
        }

        if (checkStatusBtn && status.payment_complete) {
            checkStatusBtn.style.display = 'none';
        }
        
        if (walletUriContainer && status.payment_complete) {
            walletUriContainer.style.display = 'none';
        }
    },
    
    _cleanupPaymentContainer: function() {
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

    _updatePayButtonText: function(text) {
        if (this.submitButton) {
            console.debug(`${DEBUG_TAG} Updating pay button text to:`, text);
            this.submitButton.textContent = text;
        }
    },

    _disablePaymentForm: function() {
        console.debug(`${DEBUG_TAG} Disabling payment form`);
        if (this.submitButton) {
            this.submitButton.disabled = true;
        }
        this.el.querySelectorAll('input').forEach(el => el.disabled = true);
        this.call('ui', 'block');
    },

    _enablePaymentForm: function() {
        console.debug(`${DEBUG_TAG} Enabling payment form`);
        if (this.submitButton) {
            this.submitButton.disabled = false;
        }
        this.el.querySelectorAll('input').forEach(el => el.disabled = false);
        this.call('ui', 'unblock');
    },

    _displayError: function(title, message) {
        console.debug(`${DEBUG_TAG} Displaying error dialog:`, title, message);
        this.call('dialog', 'add', ConfirmationDialog, { 
            title: title, 
            body: message,
            confirmLabel: _t("OK"),
        });
    },

    _getProviderCode: function(radio) {
        return radio.dataset.providerCode;
    },

    _getProviderId: function(radio) {
        return parseInt(radio.dataset.providerId);
    },

    destroy: function() {
        console.debug(`${DEBUG_TAG} Destroying widget`);
        if (this.submitButton) {
            this.submitButton.removeEventListener('click', this._boundOnSubmitPayment);
        }
        this._cleanupPaymentContainer();
        this._super.apply(this, arguments);
    }
});

export default publicWidget.registry.PaymentForm;
