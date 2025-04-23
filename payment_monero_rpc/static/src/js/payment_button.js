/** @odoo-module **/

import { PaymentForm } from '@payment/js/payment_form';
console.log("PaymentForm found:", PaymentForm);
import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';
import { Component } from '@odoo/owl';

class MoneroPaymentButton extends Component {
    static template = "payment_monero_rpc.MoneroPaymentButton";
    
    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification");
    }

    async handlePayment(ev) {
        ev.preventDefault();
        try {
            const result = await this.rpc("/monero/payment/initiate", {
                amount: this.props.amount,
                currency_id: this.props.currencyId,
            });
            
            if (result.redirect_url) {
                window.location = result.redirect_url;
            } else {
                this.notification.add(
                    this.env._t("Payment Error"), 
                    { type: "danger" }
                );
            }
        } catch (error) {
            this.notification.add(
                this.env._t("Payment Failed"), 
                { type: "danger" }
            );
            console.error("Monero payment error:", error);
        }
    }
}

// Register as a payment form widget
registry.category("payment_form_widgets").add("monero", MoneroPaymentButton);
