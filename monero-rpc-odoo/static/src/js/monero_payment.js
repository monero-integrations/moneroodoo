(function () {
    function init() {
        var addressDiv = document.getElementById("monero_payment_address");
        if (!addressDiv) return;

        var subaddress = addressDiv.textContent.trim();

        // Copy button
        var copyBtn = document.getElementById("copy_address_button");
        if (copyBtn) {
            copyBtn.addEventListener("click", function () {
                navigator.clipboard.writeText(subaddress).then(function () {
                    copyBtn.title = "Copied!";
                    setTimeout(function () { copyBtn.title = "Copy address to clipboard"; }, 1500);
                }).catch(function () {
                    // fallback
                    var el = document.createElement("textarea");
                    el.value = subaddress;
                    document.body.appendChild(el);
                    el.select();
                    document.execCommand("copy");
                    document.body.removeChild(el);
                });
            });
        }

        // QR button
        var qrBtn = document.getElementById("show_qr");
        if (qrBtn) {
            var qrDiv1 = document.getElementById("qr_div1");
            var qrDiv2 = document.getElementById("qr_div2");
            var qrCanvas = document.getElementById("qrcode_monero_payment");
            var qrGenerated = false;

            qrBtn.addEventListener("click", function () {
                if (!qrGenerated && qrCanvas) {
                    var amount = qrBtn.getAttribute("data-amount") || "";
                    var desc = qrBtn.getAttribute("data-description") || "";
                    var uri = "monero:" + subaddress + "?tx_amount=" + amount + "&tx_description=" + encodeURIComponent(desc);
                    // jquery.qrcode is loaded as a static asset
                    if (window.jQuery && typeof jQuery(qrCanvas).qrcode === "function") {
                        jQuery(qrCanvas).qrcode({ text: uri, width: 240, height: 240 });
                        qrGenerated = true;
                    }
                }
                if (qrDiv1) {
                    qrDiv1.style.display = qrDiv1.style.display === "block" ? "none" : "block";
                }
            });
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
