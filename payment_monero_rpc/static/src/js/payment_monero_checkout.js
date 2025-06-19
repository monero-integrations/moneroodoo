/** @odoo-module **/
import { PublicWidget } from "@web/legacy/js/public/public_widget";
import { registry } from "@web/core/registry";

const MODULE_TAG = "[MoneroCheckout]";

class MoneroCheckout extends PublicWidget {
    static selector = '.checkout_screen'; // Only targets checkout screen
    
    start() {
        console.debug(`${MODULE_TAG} Checkout screen loaded`);
        // No payment method handling here - that's in PaymentForm
        return super.start();
    }
}

registry.category("public_root_widget").add("MoneroCheckout", MoneroCheckout);
export default MoneroCheckout;
