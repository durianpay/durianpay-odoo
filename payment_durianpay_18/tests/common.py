# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.addons.payment.tests.common import PaymentCommon


class DurianpayCommon(PaymentCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.durianpay = cls._prepare_provider('durianpay', update_values={
            'durianpay_secret_key': 'dp_test_dummy_secret_key',
            'durianpay_webhook_type': 'legacy',
        })
        cls.provider = cls.durianpay
        # Durianpay only settles in IDR (no sub-unit).
        cls.currency = cls._enable_currency('IDR')

        # The Durianpay order id stored as the provider reference once the order is created.
        cls.provider_reference = 'ord_dummy_123456789'

        # A successful order-creation API response (the payment link to redirect the customer to).
        cls.order_response = {
            'data': {
                'id': cls.provider_reference,
                'payment_link_url': 'https://links.durianpay.id/payment/dummy_link_code',
            },
        }

        # A legacy webhook notification confirming the payment.
        cls.legacy_payment_data = {
            'event': 'payment.completed',
            'data': {
                'id': cls.provider_reference,
                'order_ref_id': cls.reference,
                'status': 'completed',
            },
        }

        # A SNAP virtual-account callback confirming the payment (status code '00' = completed).
        cls.snap_payment_data = {
            'paymentRequestId': cls.provider_reference,
            'trxId': cls.provider_reference,
            'additionalInfo': {
                'latestTransactionStatus': '00',
            },
            'paidAmount': {
                'value': str(cls.amount),
                'currency': 'IDR',
            },
        }
