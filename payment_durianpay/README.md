# Payment Provider: Durianpay

Adds [Durianpay](https://durianpay.id) as a payment provider in Odoo, using the
**hosted payment link** (redirect) flow.

## How it works

1. **Link creation** — when the customer pays, Odoo calls
   `POST /v1/orders` with `is_payment_link: true`
   (`models/payment_transaction.py::_durianpay_prepare_order_payload`). The Odoo
   transaction `reference` is sent as `order_ref_id`, which is the key used later to
   reconcile the webhook.
2. **Redirect** — the API returns a `payment_link_url`. Odoo embeds it as the redirect
   form `api_url` and the customer's browser is sent to Durianpay's hosted page (standard
   same-tab redirect, default Odoo behaviour). State is left to the return/webhook.
3. **Return** — on completion Durianpay redirects the customer to the **merchant-level
   redirect URL** (see below), appending `?status=completed&payment_id=…`. Point that URL at
   `/payment/durianpay/return`, which forwards to `/payment/status`. The state is *not*
   confirmed here — it only shows the polling status page.
4. **Webhook** — Durianpay notifies `/payment/durianpay/webhook`; the controller verifies the
   signature (SNAP only), finds the transaction, and sets the final state.

### Return URL (required for the customer to come back)

Durianpay payment links redirect after payment to a **single merchant-wide URL** taken from
your Durianpay merchant config (`RedirectURL`) — it is *not* a per-order API field. If unset,
Durianpay shows its own success page and the customer never returns to Odoo.

Set your merchant `RedirectURL` (Durianpay dashboard / merchant config) to:

```
https://<your-odoo>/payment/durianpay/return
```

Because the URL is merchant-wide (no transaction reference), the return controller relies on
the browser session + the webhook to resolve and finalise the transaction — it does not trust
the redirect for the payment outcome.

## Webhook types (configurable)

The provider exposes a **Webhook Type** that switches how callbacks are parsed and verified:

### Legacy ([docs](https://docs.durianpay.id/docs/webhooks-events))
- Payload shape: `{ "event": "...", "data": { ... }, "retry_count": 0 }`.
- Events handled: `payment.completed`, `order.completed`, `payment.failed`,
  `payment.expired`, `payment.cancelled`.
- Reconciled by `order_ref_id` (the Odoo transaction reference).
- **No signature verification** — Durianpay does not sign legacy webhooks, so they are
  processed as received.

### SNAP ([docs](https://docs.durianpay.id/docs/snap-virtual-account-notify-callback-handling))
- Bank Indonesia standard VA notify callback.
- Headers: `X-SIGNATURE` (base64 RSA-2048/SHA-256) and `X-TIMESTAMP`.
- Signed string: `POST:<relative_path>:<lower_hex_sha256(body)>:<X-TIMESTAMP>`.
- Verified with the **SNAP Public Key** (RSA public key, PEM) that you upload — use the
  sandbox or live key matching your secret key.
- Reconciled by `trxId` against the stored provider reference.
- Status from `additionalInfo.latestTransactionStatus`: `00` → done, `06`/`09` → error.
- Requires the `cryptography` Python library (bundled with Odoo).

## Configuration

In *Invoicing → Configuration → Payment Providers → Durianpay*:

- **Secret Key** — server-side API key. Keys prefixed with `dp_test` automatically target
  the sandbox (`https://api-sandbox.durianpay.id`); otherwise production is used.
- **API URL** — optional; overrides the API base URL (default `https://api.durianpay.id`).
  Leave empty to auto-select live/sandbox from the secret key. Useful for staging/proxy hosts.
- **Payment Link Base URL** — optional; overrides the default
  `https://links.durianpay.id/payment/` used to build the hosted link from the returned code.
  Leave empty to use the default.
- **Webhook Type** — `Legacy` (no verification) or `SNAP` (RSA-verified).
- **SNAP Public Key** — shown for SNAP; Durianpay's RSA public key (PEM).

Register the webhook URL `https://<your-odoo>/payment/durianpay/webhook` in the Durianpay
dashboard.

## Odoo version

Targets **Odoo 19**. The webhook uses the Odoo 19 payment API:
`_search_by_reference` (find tx) → `_process` → `_apply_updates` (state), with
`_extract_amount_data` returning `None` to skip the generic amount check. Partner phone uses the
transaction's `partner_phone` field (the `res.partner.mobile` field was removed in Odoo 19).

## Notes / things to confirm against your account

- **Auth** uses HTTP Basic with the secret key as the username and an empty password.
- **Currency** is restricted to `IDR`.
- **SNAP body hash**: computed over the raw request body as received (assumed already
  minified by Durianpay). Adjust `_verify_snap_signature` if your account differs.
