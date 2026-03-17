/** @odoo-module **/
import { PublicWidget } from "@web/legacy/js/public/public_widget";
import { registry } from "@web/core/registry";

const MODULE_TAG = "[MoneroCheckout]";

/**
 * Monero Checkout Widget
 * Minimal widget that runs when the checkout screen is loaded.
 * Useful for initializing Monero-specific UI state.
 * @class MoneroCheckout
 * @extends PublicWidget
 */
class MoneroCheckout extends PublicWidget {
    /**
     * CSS selector that attaches this widget to the checkout screen
     * @type {string}
     */
    static selector = '.checkout_screen';

    /**
     * Lifecycle start hook
     * Called when the widget is mounted on the page.
     * Can be used to perform setup tasks for the checkout view.
     * @returns {Promise} Promise from parent start method
     */
    start() {
        console.debug(`${MODULE_TAG} Checkout screen loaded`);
        // No payment method handling here - that's in PaymentForm
        return super.start();
    }
}

// Register the widget in the public root widget registry
registry.category("public_root_widget").add("MoneroCheckout", MoneroCheckout);
export default MoneroCheckout;
