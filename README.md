# Durianpay × Odoo — Install & Usage Guide

This repo contains the `payment_durianpay` payment provider module for Odoo.

> **Target version:** Odoo 19. The module uses the Odoo 19 payment API and is not
> compatible with 17/18 as-is.

Two setup paths are documented below:

- **Option A — Manual (macOS)** — run Odoo directly with a Python venv.
- **Option B — Docker** — run Odoo in a container (also bundles wkhtmltopdf for PDFs).

## 0. Repository layout

The guide assumes this directory structure (custom addons live outside the Odoo core):

```
odoo/
├── odoo19/              # Odoo 19 source (git clone)
└── odoo-dev/
    └── addons/
        └── payment_durianpay/   # this module
```

Custom modules are kept in `odoo-dev/addons` so they survive Odoo core updates.

## Option A — Manual setup on macOS

### A.1 Prerequisites

```sh
# Python 3.11 and PostgreSQL (via Homebrew)
brew install python@3.11 postgresql@16 git
brew services start postgresql@16
```

`wkhtmltopdf` (for printing PDF invoices) is optional and currently broken on Apple
Silicon. Skip it for development — the payment flow does not need it. (See
Troubleshooting.)

### A.2 PostgreSQL role

Create the database role Odoo will use (matching the config below):

```sh
psql postgres -c "CREATE ROLE odoo WITH LOGIN SUPERUSER PASSWORD 'odoo';"
```

If your PostgreSQL listens on a non-default port (e.g. 5433), note it for `db_port`
below.

### A.3 Clone Odoo 19

```sh
cd ~/durian/odoo
git clone https://github.com/odoo/odoo.git --branch 19.0 --depth=1 odoo19
```

### A.4 Python virtual environment + dependencies

```sh
python3.11 -m venv ~/venv/odoo19
~/venv/odoo19/bin/pip install --upgrade pip wheel setuptools
~/venv/odoo19/bin/pip install -r odoo19/requirements.txt
```

### A.5 Add the Durianpay module

Place `payment_durianpay` under `odoo-dev/addons`:

```sh
mkdir -p ~/durian/odoo/odoo-dev/addons
# copy (or git clone) the module into it:
cp -r /path/to/payment_durianpay ~/durian/odoo/odoo-dev/addons/
```

### A.6 Configuration file

Create `~/durian/odoo/odoo19/config.conf`:

```ini
[options]
db_host=localhost
db_port= 5432
db_user= odoo
db_password= odoo
addons_path= /Users/<you>/durian/odoo/odoo19/addons,/Users/<you>/durian/odoo/odoo-dev/addons
dev_mode= all
```

`addons_path` must include both Odoo's own addons and your `odoo-dev/addons`. Odoo
automatically also loads its base modules from `odoo19/odoo/addons`.

### A.7 Create the database and install base apps

From the `odoo19` directory:

```sh
cd ~/durian/odoo/odoo19

# First run: create the DB and install the apps Durianpay needs.
~/venv/odoo19/bin/python odoo-bin -c config.conf --database odoo19_dev \
  -i base,point_of_sale,payment,account --without-demo=False --stop-after-init
```

### A.8 Install the Durianpay module

```sh
~/venv/odoo19/bin/python odoo-bin -c config.conf --database odoo19_dev \
  -i payment_durianpay --stop-after-init
```

### A.9 Run Odoo

```sh
~/venv/odoo19/bin/python odoo-bin -c config.conf --database odoo19_dev --dev=all
```

Open http://localhost:8069 and log in.

### A.10 Re-apply code changes

- Python/XML changes: `--dev=all` reloads Python automatically; restart if needed.
- Manifest / data / new fields: upgrade the module:

  ```sh
  ~/venv/odoo19/bin/python odoo-bin -c config.conf --database odoo19_dev \
    -u payment_durianpay --stop-after-init
  ```

- `noupdate` data (e.g. the provider's payment-method links): a plain `-u` will not
  re-apply it on an existing record — uninstall + reinstall the module if you change
  that data.

## Option B — Docker

This builds a Linux image with all dependencies and a working `wkhtmltopdf`. The Odoo
source and addons are mounted at runtime, so live code edits apply immediately.

### B.1 Files (place in `~/durian/odoo/`)

**Dockerfile**

```dockerfile
FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates curl git \
    libpq-dev libxml2-dev libxslt1-dev libldap2-dev libsasl2-dev \
    libjpeg-dev zlib1g-dev libffi-dev libssl-dev node-less \
    fontconfig xfonts-base xfonts-75dpi \
    && rm -rf /var/lib/apt/lists/*

# Patched wkhtmltopdf (arch-aware: arm64 / amd64)
RUN set -eux; arch="$(dpkg --print-architecture)"; \
    curl -sSL -o /tmp/wk.deb \
    "https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.bookworm_${arch}.deb"; \
    apt-get update; apt-get install -y --no-install-recommends /tmp/wk.deb; \
    rm -rf /tmp/wk.deb /var/lib/apt/lists/*; wkhtmltopdf --version

COPY odoo19/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /tmp/requirements.txt

RUN mkdir -p /var/lib/odoo
VOLUME ["/var/lib/odoo"]
WORKDIR /odoo
EXPOSE 8069 8072
ENTRYPOINT ["python3", "odoo19/odoo-bin"]
CMD ["-c", "/odoo/odoo.docker.conf"]
```

**odoo.docker.conf**

```ini
[options]
db_host= host.docker.internal
db_port= 5432 ; use 5433 if your host PostgreSQL runs there
db_user= odoo
db_password= odoo
addons_path= /odoo/odoo19/addons,/odoo/odoo-dev/addons
data_dir= /var/lib/odoo
http_interface= 0.0.0.0
http_port=8069
dev_mode= all
```

**.dockerignore** (keeps the build context tiny)

```
*
!odoo19/requirements.txt
```

### B.2 Build

```sh
cd ~/durian/odoo
docker build -t odoo19-dev .
```

### B.3 Run

```sh
docker run --rm -it \
  -p 8069:8069 -p 8072:8072 \
  -v "$PWD":/odoo \
  -v odoo19-filestore:/var/lib/odoo \
  --add-host=host.docker.internal:host-gateway \
  odoo19-dev
```

PostgreSQL runs on the host, reached as `host.docker.internal`. Make sure it's running
and accepts connections from the Docker network (`pg_hba.conf`).

To create the DB / install / upgrade, append args after the image, e.g.:

```sh
docker run --rm -it -p 8069:8069 -v "$PWD":/odoo -v odoo19-filestore:/var/lib/odoo \
  --add-host=host.docker.internal:host-gateway odoo19-dev \
  -c /odoo/odoo.docker.conf -d odoo19_dev \
  -i base,point_of_sale,payment,account,payment_durianpay --without-demo=False --stop-after-init
```

## Configure the Durianpay provider

1. Log in as admin → enable Developer Mode (Settings → Developer Tools → Activate).
2. Go to **Invoicing → Configuration → Payment Providers → Durianpay**.
3. **Credentials tab:**
   - **Secret Key** — your Durianpay server key. Keys prefixed with `dp_test`
     automatically use the sandbox (`https://api-sandbox.durianpay.id`); otherwise
     production is used.
   - **API URL** (optional) — override the base URL (e.g. a staging host). Leave empty
     for auto.
   - **Payment Link Base URL** (optional) — defaults to
     `https://links.durianpay.id/payment/`.
   - **Webhook Type** — Legacy (no signature verification) or SNAP (RSA-verified).
   - **SNAP Public Key** — required only for SNAP; paste Durianpay's RSA public key
     (PEM).
4. **Configuration tab:**
   - Set a **Payment Journal** (e.g. Bank) — required for reconciliation.
   - Ensure the **Payment Methods** you want are enabled (card, qris, dana, ovo,
     shopeepay).
   - Set **State** = Test Mode (sandbox) or Enabled (production), then **Publish** it.

### Durianpay dashboard / merchant config

- **Webhook URL** (Dashboard → Settings → Webhook):
  `https://<your-odoo>/payment/durianpay/webhook`
  Enable events: `payment.completed`, `order.completed`, `payment.failed`,
  `payment.expired`, `payment.cancelled`.
- **Merchant Redirect URL** (returns the customer to the invoice after paying):
  `https://<your-odoo>/payment/durianpay/return`
  This is a merchant-wide setting in the Durianpay merchant config (not per-order).

Testing locally? Durianpay can't reach `localhost`. Expose it with a tunnel (`ngrok
http 8069` or `cloudflared tunnel --url http://localhost:8069`) and use that HTTPS URL
for both the webhook and redirect URL. Also set Odoo's `web.base.url` system parameter
to it.

### Currency (IDR) — required for Durianpay to appear

Durianpay only supports IDR, so the document being paid must be in IDR:

- **Invoicing**: activate IDR (Invoicing → Configuration → Currencies → enable IDR +
  add a rate), then set the invoice's Currency = IDR.
- **eCommerce**: the shop currency follows the website's pricelist. Create/assign a
  pricelist with Currency = IDR to the website (you do not need to change the company
  currency).

## Test a payment (sandbox)

1. Create a customer invoice in IDR, add a line, Confirm.
2. Preview / open the portal link → Pay Now → choose Durianpay.
3. You're redirected to the Durianpay hosted page; complete the sandbox payment.
4. Durianpay redirects back to `/payment/durianpay/return` → `/payment/status` → the
   invoice.
5. The webhook (`payment.completed`) confirms the transaction; the invoice becomes
   Paid.

Simulate a Legacy webhook locally (no signature needed) with the tx reference as
`order_ref_id`:

```sh
curl -i -X POST http://localhost:8069/payment/durianpay/webhook \
  -H "Content-Type: application/json" \
  -d '{"event":"payment.completed","data":{"id":"ord_xxx","order_ref_id":"INV/2026/00001","status":"completed","amount":100000}}'
```

## Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| Durianpay not shown at "Pay Now" | Provider disabled/unpublished, no Payment Journal, no payment methods linked, or the document isn't IDR. Reinstall the module if the method links are missing (the data is `noupdate`). |
| "Unable to find Wkhtmltopdf" | PDF rendering only; doesn't affect payments. Use the Docker image (has it), or ignore for dev. |
| Invoice still "Not Paid" after webhook | Reaching `done` and reconciling are separate. Run Settings → Technical → Scheduled Actions → "payment: post-process transactions" → Run Manually, or it runs automatically (~every 10 min). The browser hitting `/payment/status` also finalizes it immediately. |
| Webhook 500 / AttributeError | Ensure you're on Odoo 19 (the module targets the 19 payment API). |
| Customer not returned to invoice | Set the merchant Redirect URL to `/payment/durianpay/return` in the Durianpay dashboard. |
| Postgres "no pg_hba.conf entry" (Docker) | The container connects from the Docker network; allow that host in `pg_hba.conf`, or run Postgres in a container too. |

## Webhook reference

| Route | Method | Purpose |
|---|---|---|
| `/payment/durianpay/webhook` | POST | Receives `payment.*` / `order.*` events; confirms the transaction. |
| `/payment/durianpay/return` | GET | Customer return after payment → forwards to `/payment/status`. |

- **Legacy webhooks**: not signed (processed as received), matched by `order_ref_id`.
- **SNAP callbacks**: `X-SIGNATURE` (RSA-SHA256) verified with the configured SNAP
  public key.
