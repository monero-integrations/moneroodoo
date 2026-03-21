/** @odoo-module **/
/**
 * Monero payment confirmation page JS.
 * Handles QR code generation and clipboard copy for the Monero subaddress.
 *
 * Loaded as a frontend asset on all pages, but only activates when the
 * Monero payment confirmation elements are present in the DOM.
 */

import { loadJS } from "@web/core/assets";

// Only run on pages that have the Monero payment address element
document.addEventListener("DOMContentLoaded", async () => {
    const addressDiv = document.getElementById("monero_payment_address");
    if (!addressDiv) {
        return; // Not on a Monero payment page
    }

    const subaddress = addressDiv.textContent.trim();

    // --- Copy to clipboard ---
    const copyBtn = document.getElementById("copy_address_button");
    if (copyBtn) {
        copyBtn.addEventListener("click", async () => {
            try {
                await navigator.clipboard.writeText(subaddress);
                const originalTitle = copyBtn.getAttribute("title");
                copyBtn.setAttribute("title", "Copied!");
                setTimeout(() => copyBtn.setAttribute("title", originalTitle), 1500);
            } catch (e) {
                // Fallback for older browsers
                const el = document.createElement("textarea");
                el.value = subaddress;
                document.body.appendChild(el);
                el.select();
                document.execCommand("copy");
                document.body.removeChild(el);
            }
        });
    }

    // --- QR Code ---
    const showQrBtn = document.getElementById("show_qr");
    if (showQrBtn) {
        // Load the qrcode library dynamically
        await loadJS("/monero_rpc_odoo/static/src/js/jquery.qrcode.min.js");

        let qrShown = false;
        const qrDiv1 = document.getElementById("qr_div1");
        const qrDiv2 = document.getElementById("qr_div2");
        const qrCanvas = document.getElementById("qrcode_monero_payment");

        showQrBtn.addEventListener("click", () => {
            if (!qrShown && qrCanvas) {
                const amount = showQrBtn.dataset.amount || "";
                const description = showQrBtn.dataset.description || "";
                const recipient = showQrBtn.dataset.recipient || "";
                const uri = encodeURI(
                    `monero:${subaddress}?tx_amount=${amount}&tx_description=${description}&recipient_name=${recipient}`
                );
                // jquery.qrcode uses jQuery
                if (window.jQuery && jQuery(qrCanvas).qrcode) {
                    jQuery(qrCanvas).qrcode({ text: uri, width: 240, height: 240 });
                }
                qrShown = true;
            }
            if (qrDiv1 && qrDiv2) {
                const isVisible = qrDiv1.style.display === "block";
                qrDiv1.style.display = isVisible ? "none" : "block";
                qrDiv2.style.display = isVisible ? "none" : "block";
            }
        });
    }
});
