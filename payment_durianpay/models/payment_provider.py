# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint

import requests

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment_durianpay import const


_logger = logging.getLogger(__name__)


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
        """ Return the API base URL based on the configured secret key.

        Durianpay routes `dp_test`-prefixed keys to the sandbox environment.

        :return: The base API URL.
        :rtype: str
        """
        self.ensure_one()
        if (self.durianpay_secret_key or '').startswith('dp_test'):
            return 'https://api-sandbox.durianpay.id'
        return 'https://api.durianpay.id'

    def _durianpay_make_request(self, endpoint, payload=None, method='POST'):
        """ Make a request to Durianpay API and return the JSON-formatted content of the response.

        Note: self.ensure_one()

        :param str endpoint: The endpoint to be reached by the request.
        :param dict payload: The payload of the request.
        :param str method: The HTTP method of the request.
        :return: The JSON-formatted content of the response.
        :rtype: dict
        :raise ValidationError: If an HTTP error occurs.
        """
        self.ensure_one()

        url = f'{self._durianpay_get_api_url()}/{endpoint}'
        # Durianpay authenticates with HTTP Basic auth: the secret key as the username and an
        # empty password.
        auth = (self.durianpay_secret_key, '')
        try:
            if method == 'GET':
                response = requests.get(url, params=payload, auth=auth, timeout=10)
            else:
                response = requests.post(url, json=payload, auth=auth, timeout=10)
            response.raise_for_status()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            _logger.exception("Unable to reach endpoint at %s", url)
            raise ValidationError(
                "Durianpay: " + _("Could not establish the connection to the API.")
            )
        except requests.exceptions.HTTPError as err:
            try:
                error = err.response.json().get('error', {})
                error_message = error.get('message') or error.get('description') or err.response.text
            except ValueError:
                error_message = err.response.text
            _logger.exception(
                "Invalid API request at %s with data:\n%s", url, pprint.pformat(payload)
            )
            raise ValidationError(
                "Durianpay: " + _(
                    "The communication with the API failed. Durianpay gave us the following"
                    " information: '%s'", error_message
                )
            )
        return response.json()
