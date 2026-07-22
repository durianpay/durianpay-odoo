# Part of Odoo. See LICENSE file for full copyright and licensing details.

# The currencies supported by Durianpay, in ISO 4217 format.
# Durianpay is an Indonesian payment gateway and settles in IDR.
SUPPORTED_CURRENCIES = [
    'IDR',
]

# Mapping of currencies to the number of decimal places Durianpay expects.
# IDR has no sub-unit, so amounts are sent without decimals.
# https://docs.durianpay.id/docs/create-payment-link-via-api
CURRENCY_DECIMALS = {
    'IDR': 0,
}

# The default base domains serving hosted payment links when the API returns a bare code.
# Selected based on the secret key prefix (sandbox for `dp_test` keys); overridable per
# provider via `durianpay_link_base_url`.
DEFAULT_LINK_BASE_URL = 'https://links.durianpay.id/payment/'
DEFAULT_SANDBOX_LINK_BASE_URL = 'https://links-sandbox.durianpay.id/payment/'

# The codes of the payment methods to activate when Durianpay is activated.
# The hosted payment link surfaces every method enabled on the merchant's
# Durianpay dashboard; these are the generic Odoo codes that map to them.
DEFAULT_PAYMENT_METHOD_CODES = {
    'card',
    'qris',
    'dana',
    'ovo',
    'shopeepay',
}

# Mapping of transaction states to Durianpay payment statuses and webhook events.
# Durianpay notifies via `payment.completed`, `payment.failed`, `payment.cancelled`
# events; the order/payment `status` field is used as a fallback.
# https://docs.durianpay.id/docs/payment-api-integration-steps
PAYMENT_STATUS_MAPPING = {
    'pending': ('pending', 'processing', 'initiated', 'start'),
    'done': ('completed', 'paid', 'success', 'settled', 'capture'),
    'cancel': ('cancelled', 'canceled', 'expired'),
    'error': ('failed', 'failure', 'denied'),
}

# Mapping of Durianpay legacy webhook event names to the transaction state to apply.
# https://docs.durianpay.id/docs/webhooks-events
PAYMENT_EVENT_MAPPING = {
    'payment.completed': 'done',
    'order.completed': 'done',
    'payment.failed': 'error',
    'payment.expired': 'cancel',
    'payment.cancelled': 'cancel',
}

# Mapping of SNAP `latestTransactionStatus` codes to the transaction state to apply.
# https://docs.durianpay.id/docs/snap-virtual-account-notify-callback-handling
SNAP_STATUS_MAPPING = {
    'done': ('00',),  # Completed; funds settle to the merchant.
    'error': ('06', '09'),  # 06 = failed, 09 = rejected (funds refunded).
}
