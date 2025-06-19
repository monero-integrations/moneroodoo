/** @odoo-module **/

import { OnlinePaymentPopup } from "@pos_online_payment/app/online_payment_popup/online_payment_popup";
import { useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";

export class MoneroPaymentPopup extends OnlinePaymentPopup {
    static template = "payment_monero_rpc.MoneroPaymentPopup";
    static components = OnlinePaymentPopup.components || {};
    
    static props = {
        ...OnlinePaymentPopup.props,
        qrCode: { type: String },
        formattedAmount: { type: String },
        formattedMoneroAmount: { type: String },
        orderName: { type: String },
        exchangeRate: { type: String },
        sellerAddress: { type: String },
        confirmationCount: { type: Number },
        close: { type: Function, optional: true },
    };
        
    setup() {
        super.setup();
        this.notification = useService("notification");
        
        this.state = useState({
            ...(this.state || {}),
            paymentStatus: 'pending',
            countdown: 900, // 15 minutes
        });        
        
        this.timer = setInterval(() => {
            if (this.state.countdown > 0) {
                this.state.countdown--;
            } else {
                clearInterval(this.timer);
                this.props.close?.();
            }
        }, 1000);
    }
    
    willUnmount() {
        super.willUnmount?.();
        clearInterval(this.timer);
    }
    
    copyToClipboard(text) {
        try {
            navigator.clipboard.writeText(text);
            this.notification.add('Copied to clipboard!', {
                type: 'success',
            });
        } catch (err) {
            console.error('Failed to copy text: ', err);
            this.notification.add('Failed to copy to clipboard', {
                type: 'danger',
            });
        }
    }
    
    
    // New method to handle Monero amount copy
    copyMoneroAmount() {
        this.copyToClipboard(this.props.formattedMoneroAmount);
    }
    
    // New method to handle seller address copy
    copySellerAddress() {
        this.copyToClipboard(this.props.sellerAddress);
    }
}

registry.category("pos.popups").add("payment_monero_rpc.MoneroPaymentPopup", MoneroPaymentPopup);
registry.category("dialogs").add("MoneroPaymentPopup", {
    component: MoneroPaymentPopup,
});
