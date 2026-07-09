# Durianpay × Odoo

Odoo 19 payment provider module for [Durianpay](https://durianpay.id), Indonesia's
payment gateway. It plugs into Odoo's standard `payment` app so Durianpay shows up
alongside any other payment provider at checkout, on invoices, and on the customer
portal — no changes needed to sales, invoicing, or eCommerce flows.

## Features

- **Hosted payment link (redirect) flow** — Odoo creates the order via the Durianpay
  API and redirects the customer to Durianpay's hosted checkout page.
- **Multiple payment methods** — card, QRIS, DANA, OVO, ShopeePay.
- **Two webhook modes** — Legacy (unsigned) and SNAP (RSA-signed, Bank Indonesia
  standard), selectable per provider.
- **Sandbox/live auto-detection** — `dp_test`-prefixed secret keys automatically route
  to the sandbox API; override the API URL manually if needed (e.g. staging).
- **IDR-only**, matching Durianpay's supported currency.

## Repo layout

- [`payment_durianpay/`](./payment_durianpay) — the Odoo module itself (models,
  controllers, views, tests).
- [`payment_durianpay/README.md`](./payment_durianpay/README.md) — how the module
  works internally: request/webhook flow, configuration fields, webhook payload
  formats.
- [`payment_durianpay/INSTALL.md`](./payment_durianpay/INSTALL.md) — install & usage
  guide: setting up Odoo 19 from source (manual macOS or Docker), installing the
  module, configuring the provider, and testing a sandbox payment end to end.

## Requirements

- Odoo 19 (uses the Odoo 19 `payment` module API; not compatible with earlier
  versions without porting).
- A Durianpay merchant account with API credentials (sandbox and/or live secret key).

## Quick start

See [`payment_durianpay/INSTALL.md`](./payment_durianpay/INSTALL.md) for full setup
instructions. In short: clone Odoo 19, drop this module into your custom addons path,
install it, then configure the Durianpay provider under *Invoicing → Configuration →
Payment Providers*.
