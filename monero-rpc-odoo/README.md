# monero-rpc-odoo

Accept Monero (XMR) payments in your Odoo 19 eCommerce shop via a self-hosted `monero-wallet-rpc`.

---

## Requirements

- Odoo 19.0
- Python 3.10+
- [`monero`](https://pypi.org/project/monero/) Python package (`pip install monero`)
- A synced `monerod` node
- A running `monero-wallet-rpc` instance (view-key wallet recommended)

---

## Installation

1. Copy the `monero-rpc-odoo` folder into your Odoo addons directory.
2. Restart Odoo.
3. Go to **Apps** → search for `monero_rpc_odoo` → **Install**.

---

## Configuration

### 1. Monero Wallet RPC

Start `monero-wallet-rpc` with a view-only wallet:

```bash
monero-wallet-rpc \
  --wallet-file /path/to/viewonly.wallet \
  --rpc-bind-port 18082 \
  --rpc-login user:password \
  --disable-rpc-login   # or keep login for security
```

See the [Monero Wallet RPC docs](https://www.getmonero.org/resources/developer-guides/wallet-rpc.html) for full options.

### 2. Odoo Payment Provider

1. Go to **Website → Configuration → Payment Providers**.
2. Find **Monero** and click **Configure**.
3. Fill in:
   - **RPC Host** — IP or hostname of your `monero-wallet-rpc` (default: `127.0.0.1`)
   - **RPC Port** — port (default: `18082`)
   - **RPC User / Password** — if authentication is enabled
   - **Security Level** — number of confirmations required (0 = instant, 10 = high security)
4. Set the provider to **Enabled**.

### 3. XMR Currency

1. Go to **Accounting → Configuration → Currencies**.
2. Find **XMR** and set it to **Active**.
3. The exchange rate is updated automatically every 15 minutes from CoinGecko.

---

## Usage

- Customers browsing your eCommerce shop can select **Monero** at checkout.
- They are shown a unique subaddress and QR code with the exact XMR amount to send.
- The payment is detected automatically. The page redirects to the order confirmation once payment is received.
- Products can be priced in USD (or any currency) — the XMR amount is calculated at checkout using the live rate.

---

## Security

- Each order gets a unique, one-time subaddress — no address reuse.
- Use a **view-only wallet** on the server so the RPC cannot spend funds.
- Set a higher confirmation level for large orders.

---


## 🌐 Live Demo

The demo runs on a self-hosted Odoo 19 instance tunnelled through **ngrok** — providing a public HTTPS URL without a dedicated server or SSL certificate.

**Demo store:** https://griffinish-yuette-nonevadingly.ngrok-free.app

Browse products, go through checkout, and pay with stagenet XMR.

- **Guest checkout enabled** — no account required
- **Privacy tip:** Use any name and a dummy email — no personal details are required or verified
- Uses **Monero Stagenet (sXMR)** — NOT real XMR. Do not send real funds.

Get free stagenet XMR: https://cypherfaucet.com/xmr-stagenet

[▶ Watch the video walkthrough](https://youtu.be/4L7DzkyNuYI?si=tHmj3XkGnLrgoi3v)

![Products](./static/src/img/screenshots/products-page.png)
![Status](./static/src/img/screenshots/payment-status.png)
![Confirmation](./static/src/img/screenshots/confirmation-page.png)

---

## Exposing Odoo with ngrok

ngrok is the easiest way to get a public HTTPS URL for a local or server-hosted Odoo instance — useful for demos, testing webhooks, or sharing access without a domain.

**1. Install ngrok**

```bash
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
  | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
  | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install ngrok
```

**2. Authenticate**

```bash
ngrok config add-authtoken YOUR_TOKEN
```

Get your token at https://dashboard.ngrok.com

**3. Start the tunnel**

```bash
ngrok http 8069
```

ngrok prints a public HTTPS URL (e.g. `https://abc123.ngrok-free.app`) that forwards to your Odoo instance.

**4. Configure Odoo**

Add to `odoo.conf`:

```ini
proxy_mode = True
```

Then go to **Settings → Technical → System Parameters** and set `web.base.url` to your ngrok URL.


---

## Bug Tracker

Report issues on [GitHub Issues](https://github.com/monero-integrations/moneroodoo/issues).

---

## Credits

**Maintainer:** [Monero Integrations](https://github.com/monero-integrations)


