# Part of Odoo. See LICENSE file for full copyright and licensing details.

from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment.tests.http_common import PaymentHttpCommon
from odoo.addons.payment_durianpay import const
from odoo.addons.payment_durianpay.controllers.main import DurianpayController
from odoo.addons.payment_durianpay.tests.common import DurianpayCommon


# Odoo 18: API calls go through _durianpay_make_request on the provider model.
_MAKE_REQUEST = (
    'odoo.addons.payment_durianpay.models.payment_provider.PaymentProvider._durianpay_make_request'
)

# Base-class path for `_handle_notification_data` defined by the `payment` framework (Odoo 18).
_HANDLE_NOTIFICATION_DATA = (
    'odoo.addons.payment.models.payment_transaction.PaymentTransaction._handle_notification_data'
)


@tagged('post_install', '-at_install')
class DurianpayTest(DurianpayCommon, PaymentHttpCommon):

    # === TESTS: ORDER PAYLOAD === #

    def test_order_payload_values(self):
        """ Test that the order payload is built with the expected values. """
        tx = self._create_transaction(flow='redirect')
        payload = tx._durianpay_prepare_order_payload()

        # IDR has no sub-unit; the amount must be sent without decimals.
        self.assertEqual(payload['amount'], '1111')
        self.assertEqual(payload['currency'], 'IDR')
        self.assertEqual(payload['order_ref_id'], tx.reference)
        self.assertTrue(payload['is_payment_link'])
        self.assertEqual(payload['customer']['given_name'], tx.partner_name)
        self.assertEqual(payload['customer']['email'], tx.partner_email)

    # === TESTS: RENDERING VALUES === #

    def test_rendering_values_return_payment_link(self):
        """ Test that the rendering values expose the hosted payment link and store the order id. """
        tx = self._create_transaction(flow='redirect')
        with patch(_MAKE_REQUEST, return_value=self.order_response):
            rendering_values = tx._get_specific_rendering_values(None)

        self.assertEqual(
            rendering_values['api_url'], self.order_response['data']['payment_link_url']
        )
        self.assertEqual(tx.provider_reference, self.provider_reference)

    def test_rendering_values_prepend_base_url_to_bare_code(self):
        """ Test that a bare link code is prefixed with the configured base URL. """
        tx = self._create_transaction(flow='redirect')
        with patch(
            _MAKE_REQUEST,
            return_value={'data': {'id': self.provider_reference, 'payment_link_url': 'abc123'}},
        ):
            rendering_values = tx._get_specific_rendering_values(None)

        self.assertEqual(
            rendering_values['api_url'],
            f'{self.provider._durianpay_get_link_base_url()}abc123',
        )

    def test_rendering_values_without_link_raises(self):
        """ Test that a missing payment link in the response raises a ValidationError. """
        tx = self._create_transaction(flow='redirect')
        with patch(_MAKE_REQUEST, return_value={'data': {'id': 'ord_1'}}):
            with self.assertRaises(ValidationError):
                tx._get_specific_rendering_values(None)

    # === TESTS: PROVIDER CONFIGURATION === #

    def test_supported_currencies_are_limited_to_idr(self):
        """ Test that only IDR is reported as a supported currency. """
        supported = self.provider._get_supported_currencies()
        self.assertEqual(set(supported.mapped('name')), set(const.SUPPORTED_CURRENCIES))

    def test_default_payment_method_codes(self):
        """ Test that the default payment method codes match the constant. """
        self.assertEqual(
            self.provider._get_default_payment_method_codes(),
            const.DEFAULT_PAYMENT_METHOD_CODES,
        )

    def test_api_url_selection(self):
        """ Test the resolution of the API URL based on the key prefix. """
        # `dp_test`-prefixed key targets the sandbox.
        self.provider.durianpay_secret_key = 'dp_test_key'
        self.assertEqual(self.provider._durianpay_get_api_url(), 'https://api-sandbox.durianpay.id')

        # A live key targets production.
        self.provider.durianpay_secret_key = 'dp_live_key'
        self.assertEqual(self.provider._durianpay_get_api_url(), 'https://api.durianpay.id')

    # === TESTS: GET TX FROM NOTIFICATION DATA === #

    def test_get_tx_from_notification_data_legacy(self):
        """ Test that a legacy notification finds the transaction by its Odoo reference. """
        tx = self._create_transaction(flow='redirect')
        found = self.env['payment.transaction']._get_tx_from_notification_data(
            'durianpay', {'order_ref_id': tx.reference}
        )
        self.assertEqual(found, tx)

    def test_get_tx_from_notification_data_snap(self):
        """ Test that a SNAP notification finds the transaction by its provider reference. """
        tx = self._create_transaction(flow='redirect', provider_reference=self.provider_reference)
        found = self.env['payment.transaction']._get_tx_from_notification_data(
            'durianpay', {'trx_id': self.provider_reference}
        )
        self.assertEqual(found, tx)

    @mute_logger('odoo.addons.payment_durianpay.models.payment_transaction')
    def test_get_tx_from_notification_data_missing_raises(self):
        """ Test that an unmatched reference raises a ValidationError. """
        with self.assertRaises(ValidationError):
            self.env['payment.transaction']._get_tx_from_notification_data(
                'durianpay', {'order_ref_id': 'does-not-exist'}
            )

    @mute_logger('odoo.addons.payment_durianpay.models.payment_transaction')
    def test_get_tx_from_notification_data_missing_reference_raises(self):
        """ Test that missing reference fields raise a ValidationError. """
        with self.assertRaises(ValidationError):
            self.env['payment.transaction']._get_tx_from_notification_data('durianpay', {})

    # === TESTS: PROCESS NOTIFICATION DATA === #

    def test_process_notification_data_sets_states_from_event(self):
        """ Test that the transaction state is resolved from the webhook event. """
        cases = {
            'payment.completed': 'done',
            'payment.failed': 'error',
            'payment.expired': 'cancel',
            'payment.cancelled': 'cancel',
        }
        for event, expected_state in cases.items():
            tx = self._create_transaction(flow='redirect', reference=f'tx-{event}')
            tx._process_notification_data({'event': event, 'id': self.provider_reference})
            self.assertEqual(tx.state, expected_state)

    def test_process_notification_data_falls_back_to_status(self):
        """ Test that the state falls back to the `status` field when no event is mapped. """
        tx = self._create_transaction(flow='redirect', reference='tx-status-done')
        tx._process_notification_data({'status': 'settled'})
        self.assertEqual(tx.state, 'done')

        tx_pending = self._create_transaction(flow='redirect', reference='tx-status-pending')
        tx_pending._process_notification_data({'status': 'initiated'})
        self.assertEqual(tx_pending.state, 'pending')

    # === TESTS: WEBHOOK NORMALIZATION === #

    def test_is_snap_notification(self):
        """ Test the detection of SNAP callbacks versus legacy webhooks. """
        self.assertTrue(DurianpayController._is_snap_notification(self.snap_payment_data))
        self.assertFalse(DurianpayController._is_snap_notification(self.legacy_payment_data))

    def test_normalize_legacy_data(self):
        """ Test that a legacy payload is flattened with its event. """
        normalized = DurianpayController._normalize_legacy_data(self.legacy_payment_data)
        self.assertEqual(normalized['event'], 'payment.completed')
        self.assertEqual(normalized['order_ref_id'], self.reference)

    def test_normalize_snap_data(self):
        """ Test that a SNAP payload is mapped onto the common notification fields. """
        normalized = DurianpayController._normalize_snap_data(self.snap_payment_data)
        self.assertEqual(normalized['id'], self.provider_reference)
        self.assertEqual(normalized['trx_id'], self.provider_reference)
        self.assertEqual(normalized['status'], 'completed')

    # === TESTS: WEBHOOK (HTTP) === #

    @mute_logger(
        'odoo.addons.payment_durianpay.controllers.main',
        'odoo.addons.payment.models.payment_transaction',
    )
    def test_legacy_webhook_confirms_transaction(self):
        """ Test that a legacy webhook notification confirms the transaction. """
        tx = self._create_transaction(flow='redirect')
        url = self._build_url(DurianpayController._webhook_url)
        self._make_json_request(url, data=self.legacy_payment_data)
        self.assertEqual(tx.state, 'done')

    @mute_logger('odoo.addons.payment_durianpay.controllers.main')
    def test_snap_webhook_triggers_signature_check(self):
        """ Test that a SNAP callback triggers the RSA signature verification. """
        self.provider.durianpay_webhook_type = 'snap'
        self._create_transaction(flow='redirect', provider_reference=self.provider_reference)
        url = self._build_url(DurianpayController._webhook_url)
        with patch.object(
            DurianpayController, '_verify_snap_signature',
        ) as signature_check_mock, patch(_HANDLE_NOTIFICATION_DATA):
            self._make_json_request(url, data=self.snap_payment_data)
        self.assertEqual(signature_check_mock.call_count, 1)
