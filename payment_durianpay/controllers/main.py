# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import binascii
import hashlib
import logging
import pprint

from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment_durianpay_18 import const


_logger = logging.getLogger(__name__)


class DurianpayController(http.Controller):

    _webhook_url = '/payment/durianpay/webhook'
    _return_url = '/payment/durianpay/return'

    @http.route(_return_url, type='http', methods=['GET'], auth='public')
    def durianpay_return(self, **data):
        """ Redirect the customer to the payment status page after returning from Durianpay.

        The transaction state is confirmed asynchronously through the webhook, so this route
        only sends the customer back to Odoo.
        """
        _logger.info("Handling redirection from Durianpay with data:\n%s", pprint.pformat(data))
        return request.redirect('/payment/status')

    @http.route(_webhook_url, type='http', methods=['POST'], auth='public', csrf=False)
    def durianpay_webhook(self):
        """ Process the notification data sent by Durianpay to the webhook.

        Both the Legacy webhook format and the SNAP callback format are supported; the format
        used is determined by the provider's `durianpay_webhook_type` configuration.

        :return: An empty HTTP 200 response to acknowledge the notification.
        """
        raw_body = request.httprequest.get_data()
        data = request.get_json_data()
        _logger.info("Notification received from Durianpay with data:\n%s", pprint.pformat(data))

        is_snap = self._is_snap_notification(data)
        notification_data = (
            self._normalize_snap_data(data) if is_snap else self._normalize_legacy_data(data)
        )

        try:
            tx_sudo = request.env['payment.transaction'].sudo()._get_tx_from_notification_data(
                'durianpay', notification_data
            )
            # Verify the authenticity of the notification before processing it.
            self._verify_notification(tx_sudo, data, notification_data, raw_body, is_snap)

            # Handle the notification data.
            tx_sudo._handle_notification_data('durianpay', notification_data)
        except ValidationError:
            _logger.exception("Unable to handle notification data; skipping to acknowledge.")

        return request.make_json_response('')

    # === HELPERS - NORMALIZATION === #

    @staticmethod
    def _is_snap_notification(data):
        """ Detect whether the payload is a SNAP callback rather than a legacy webhook.

        SNAP callbacks follow the Bank Indonesia standard and expose fields such as
        `paymentRequestId` and `virtualAccountNo`, whereas legacy webhooks wrap the entity in a
        top-level `event`/`data` structure.

        :param dict data: The parsed webhook payload.
        :return: Whether the payload is a SNAP callback.
        :rtype: bool
        """
        return bool(data.get('paymentRequestId') or data.get('virtualAccountNo')) \
            and 'event' not in data

    @staticmethod
    def _normalize_legacy_data(data):
        """ Flatten a legacy webhook payload into a single notification dict.

        :param dict data: The parsed webhook payload (`{event, data, ...}`).
        :return: The normalized notification data.
        :rtype: dict
        """
        notification_data = dict(data.get('data') or {})
        notification_data['event'] = data.get('event')
        return notification_data

    @staticmethod
    def _normalize_snap_data(data):
        """ Map a SNAP callback payload onto the common notification dict.

        :param dict data: The parsed SNAP callback payload.
        :return: The normalized notification data.
        :rtype: dict
        """
        additional_info = data.get('additionalInfo') or {}
        status_code = additional_info.get('latestTransactionStatus')
        if status_code in const.SNAP_STATUS_MAPPING['done']:
            status = 'completed'
        elif status_code in const.SNAP_STATUS_MAPPING['error']:
            status = 'failed'
        else:
            status = status_code
        return {
            'id': data.get('paymentRequestId') or data.get('trxId'),
            'trx_id': data.get('trxId'),
            'status': status,
            'amount': (data.get('paidAmount') or {}).get('value'),
        }

    # === HELPERS - SIGNATURE VERIFICATION === #

    def _verify_notification(self, tx_sudo, payload, notification_data, raw_body, is_snap):
        """ Verify the authenticity of the notification according to the webhook type.

        Legacy webhooks are not signed by Durianpay and are therefore accepted as-is; only SNAP
        callbacks are cryptographically verified.

        :param payment.transaction tx_sudo: The transaction referenced by the notification.
        :param dict payload: The full parsed payload.
        :param dict notification_data: The normalized notification data.
        :param bytes raw_body: The raw request body, as received.
        :param bool is_snap: Whether the payload is a SNAP callback.
        :return: None
        :raise Forbidden: If the verification fails.
        """
        if is_snap or tx_sudo.provider_id.durianpay_webhook_type == 'snap':
            self._verify_snap_signature(tx_sudo, raw_body)

    def _verify_snap_signature(self, tx_sudo, raw_body):
        """ Verify the asymmetric (RSA-SHA256) signature of a SNAP callback.

        The `X-SIGNATURE` header carries a base64-encoded RSA signature over the string
        `<METHOD>:<RELATIVE_PATH>:<lower_hex_sha256(body)>:<X-TIMESTAMP>`, verified with
        Durianpay's public key.
        See https://docs.durianpay.id/docs/snap-virtual-account-notify-callback-handling

        :param payment.transaction tx_sudo: The transaction referenced by the notification.
        :param bytes raw_body: The raw request body, as received.
        :return: None
        :raise Forbidden: If the signature is missing, malformed, or invalid.
        """
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.exceptions import InvalidSignature
        except ImportError:
            _logger.error("Cannot verify SNAP notification: the `cryptography` library is missing.")
            raise Forbidden()

        received_signature = request.httprequest.headers.get('X-SIGNATURE')
        timestamp = request.httprequest.headers.get('X-TIMESTAMP')
        if not received_signature or not timestamp:
            _logger.warning("Received SNAP notification with missing signature or timestamp.")
            raise Forbidden()

        public_key_pem = tx_sudo.provider_id.durianpay_snap_public_key
        if not public_key_pem:
            _logger.warning("Cannot verify SNAP notification: no public key configured.")
            raise Forbidden()

        body_hash = hashlib.sha256(raw_body).hexdigest().lower()
        method = request.httprequest.method
        relative_path = request.httprequest.path
        string_to_verify = f"{method}:{relative_path}:{body_hash}:{timestamp}"

        try:
            public_key = serialization.load_pem_public_key(public_key_pem.strip().encode())
            public_key.verify(
                base64.b64decode(received_signature),
                string_to_verify.encode(),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except (InvalidSignature, ValueError, TypeError, binascii.Error):
            _logger.warning("Received SNAP notification with invalid signature.")
            raise Forbidden()
