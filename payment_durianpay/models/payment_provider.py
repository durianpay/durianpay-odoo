# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models

from odoo.addons.payment_durianpay import const


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('durianpay', "Durianpay")], ondelete={'durianpay': 'set default'}
    )
    durianpay_secret_key = fields.Char(
        string="Durianpay Secret Key",
        help="The server-side API key. Keys prefixed with `dp_test` target the sandbox.",
        groups='base.group_system',
        required_if_provider='durianpay',
    )
    durianpay_webhook_type = fields.Selection(
        selection=[('legacy', "Legacy"), ('snap', "SNAP")],
        string="Durianpay Webhook Type",
        help="The format of the webhook notifications to process:\n"
             "- Legacy: classic Durianpay webhooks (no signature verification).\n"
             "- SNAP: Bank Indonesia SNAP callbacks verified with Durianpay's RSA public key.",
        default='legacy',
        required_if_provider='durianpay',
    )
    durianpay_snap_public_key = fields.Text(
        string="Durianpay SNAP Public Key",
        help="Durianpay's RSA public key (PEM format) used to verify the X-SIGNATURE of SNAP "
             "callbacks. Use the sandbox or live key matching your secret key.",
        groups='base.group_system',
    )
    durianpay_api_url = fields.Char(
        string="Durianpay API URL",
        help="Base URL of the Durianpay API (e.g. %s). Leave empty to select automatically "
             "between the live and sandbox URLs based on the secret key's `dp_test` prefix."
             % const.DEFAULT_API_URL,
        groups='base.group_system',
    )
    durianpay_link_base_url = fields.Char(
        string="Durianpay Payment Link Base URL",
        help="Base URL prepended to the payment link code returned by the API. Leave empty to "
             "use the default (%s)." % const.DEFAULT_LINK_BASE_URL,
        groups='base.group_system',
    )

    # === BUSINESS METHODS - PAYMENT FLOW === #

    def _get_supported_currencies(self):
        """ Override of `payment` to return the supported currencies. """
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'durianpay':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _get_default_payment_method_codes(self):
        """ Override of `payment` to return the default payment method codes. """
        default_codes = super()._get_default_payment_method_codes()
        if self.code != 'durianpay':
            return default_codes
        return const.DEFAULT_PAYMENT_METHOD_CODES

    def _durianpay_get_link_base_url(self):
        """ Return the base URL used to build hosted payment links.

        Falls back to the default when no override is configured.

        :return: The payment link base URL, with a trailing slash.
        :rtype: str
        """
        self.ensure_one()
        base_url = (self.durianpay_link_base_url or const.DEFAULT_LINK_BASE_URL).strip()
        return base_url if base_url.endswith('/') else f'{base_url}/'

    def _durianpay_get_api_url(self):
        """ Return the API base URL to use for requests.

        Uses the configured override if set; otherwise routes `dp_test`-prefixed keys to the
        sandbox environment and other keys to production.

        :return: The base API URL, without a trailing slash.
        :rtype: str
        """
        self.ensure_one()
        if self.durianpay_api_url:
            return self.durianpay_api_url.strip().rstrip('/')
        if (self.durianpay_secret_key or '').startswith('dp_test'):
            return const.DEFAULT_SANDBOX_API_URL
        return const.DEFAULT_API_URL

    # === REQUEST HELPERS === #

    def _build_request_url(self, endpoint, **kwargs):
        """ Override of `payment` to build the request URL. """
        if self.code != 'durianpay':
            return super()._build_request_url(endpoint, **kwargs)
        return f'{self._durianpay_get_api_url()}/{endpoint}'

    def _build_request_auth(self, **kwargs):
        """ Override of `payment` to build the request HTTP Basic auth.

        Durianpay authenticates with the secret key as the username and an empty password.
        """
        if self.code != 'durianpay':
            return super()._build_request_auth(**kwargs)
        return (self.durianpay_secret_key, '')

    def _parse_response_error(self, response):
        """ Override of `payment` to extract the error message from a Durianpay response. """
        if self.code != 'durianpay':
            return super()._parse_response_error(response)
        return self._durianpay_extract_error(response)

    @staticmethod
    def _durianpay_extract_error(response):
        """ Extract a human-readable error message from a Durianpay error response.

        Durianpay error bodies are not uniform: `error` may be a dict (`{code, description}`),
        a plain string, and the body may also carry `message`/`errors`. This handles all shapes
        and falls back to the raw text.

        :param response: The `requests` response object.
        :return: The best-effort error message.
        :rtype: str
        """
        try:
            body = response.json()
        except ValueError:
            return response.text

        if isinstance(body, str):
            return body
        if isinstance(body, dict):
            error = body.get('error')
            if isinstance(error, dict):
                return (
                    error.get('message')
                    or error.get('description')
                    or error.get('code')
                    or response.text
                )
            # `errors` is often a list of field-level validation messages.
            errors = body.get('errors')
            if isinstance(errors, (list, tuple)) and errors:
                return '; '.join(str(e) for e in errors)
            return (
                (error if isinstance(error, str) else None)
                or body.get('message')
                or body.get('error_code')
                or response.text
            )
        return response.text
