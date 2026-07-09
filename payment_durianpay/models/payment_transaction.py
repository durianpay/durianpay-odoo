# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint
import re

from odoo import _, models
from odoo.exceptions import ValidationError
from odoo.tools import float_round

from odoo.addons.payment_durianpay import const


_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _get_specific_rendering_values(self, processing_values):
        """ Override of `payment` to return Durianpay-specific rendering values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic and specific processing values of the transaction
        :return: The dict of provider-specific rendering values.
        :rtype: dict
        """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'durianpay':
            return res

        # Create the order as a payment link and retrieve its hosted URL.
        payload = self._durianpay_prepare_order_payload()
        _logger.info(
            "Sending order request for payment link creation:\n%s", pprint.pformat(payload)
        )
        order_data = self._send_api_request('POST', 'v1/orders', json=payload)
        _logger.info("Received order request response:\n%s", pprint.pformat(order_data))

        data = order_data.get('data', order_data)

        # Persist the Durianpay order id so the webhook can be reconciled.
        self.provider_reference = data.get('id')

        # Extract the payment link URL and embed it in the redirect form.
        payment_link = data.get('payment_link_url') or data.get('checkout_url')
        if payment_link and not payment_link.startswith('http'):
            payment_link = f'{self.provider_id._durianpay_get_link_base_url()}{payment_link}'
        if not payment_link:
            raise ValidationError(
                "Durianpay: " + _("The API did not return a payment link URL.")
            )

        return {
            'api_url': payment_link,
        }

    def _durianpay_prepare_order_payload(self):
        """ Create the payload for the order (payment link) request.

        :return: The request payload.
        :rtype: dict
        """
        if self.currency_id.name in const.CURRENCY_DECIMALS:
            rounding = const.CURRENCY_DECIMALS.get(self.currency_id.name)
        else:
            rounding = self.currency_id.decimal_places
        rounded_amount = float_round(self.amount, rounding, rounding_method='DOWN')

        customer = {
            'given_name': self.partner_name,
        }
        if self.partner_email:
            customer['email'] = self.partner_email
        if phone := self._durianpay_format_phone(self.partner_phone):
            customer['mobile'] = phone

        payload = {
            'amount': f'{rounded_amount:.{rounding}f}',
            'currency': self.currency_id.name,
            'order_ref_id': self.reference,
            'is_payment_link': True,
            'customer': customer,
        }
        return payload

    @staticmethod
    def _durianpay_format_phone(phone):
        """ Strip formatting characters Durianpay rejects (notably the leading `+`).

        Keeps only the digits (removing `+`, spaces, dashes, parentheses). Returns False when
        nothing usable remains so the optional field is omitted instead of failing validation.

        :param str phone: The raw phone number.
        :return: The digits-only phone number, or False.
        :rtype: str | bool
        """
        if not phone:
            return False
        return re.sub(r'\D', '', phone) or False

    def _search_by_reference(self, provider_code, payment_data):
        """ Override of `payment` to find the transaction based on the payment data.

        Legacy webhooks carry `order_ref_id` (the Odoo reference); SNAP callbacks carry
        `trx_id`, which is reconciled against the stored provider reference.

        :param str provider_code: The code of the provider handling the transaction.
        :param dict payment_data: The payment data sent by the provider.
        :return: The transaction, if found.
        :rtype: payment.transaction
        """
        if provider_code != 'durianpay':
            return super()._search_by_reference(provider_code, payment_data)

        reference = payment_data.get('order_ref_id')
        if reference:
            tx = self.search([('reference', '=', reference), ('provider_code', '=', 'durianpay')])
        else:
            provider_reference = payment_data.get('trx_id') or payment_data.get(
                'provider_reference'
            )
            if not provider_reference:
                _logger.warning("Received Durianpay data with missing reference.")
                return self
            tx = self.search([
                ('provider_reference', '=', provider_reference),
                ('provider_code', '=', 'durianpay'),
            ])
        if not tx:
            _logger.warning(
                "No Durianpay transaction found matching reference %s.",
                reference or payment_data.get('trx_id'),
            )
        return tx

    def _extract_amount_data(self, payment_data):
        """ Override of `payment` to opt out of the generic amount validation.

        The Durianpay notification does not reliably carry the currency, so the amount check is
        skipped (returning `None` tells the framework to skip it); reconciliation still verifies
        the amount against the invoice.
        """
        if self.provider_code != 'durianpay':
            return super()._extract_amount_data(payment_data)
        return None

    def _apply_updates(self, payment_data):
        """ Override of `payment` to update the transaction based on the payment data.

        Note: self.ensure_one()

        :param dict payment_data: The payment data sent by the provider.
        :return: None
        """
        if self.provider_code != 'durianpay':
            return super()._apply_updates(payment_data)

        # Update the provider reference with the Durianpay payment/order id.
        self.provider_reference = payment_data.get('id') or self.provider_reference

        # Resolve the target state from the webhook event, falling back to the status field.
        event = payment_data.get('event')
        target_state = const.PAYMENT_EVENT_MAPPING.get(event)
        if not target_state:
            payment_status = (payment_data.get('status') or '').lower()
            for state, statuses in const.PAYMENT_STATUS_MAPPING.items():
                if payment_status in statuses:
                    target_state = state
                    break

        if target_state == 'pending':
            self._set_pending()
        elif target_state == 'done':
            self._set_done()
        elif target_state == 'cancel':
            self._set_canceled()
        elif target_state == 'error':
            failure_reason = payment_data.get('failure_reason') or payment_data.get('message')
            self._set_error(_(
                "An error occurred during the processing of your payment (%s). Please try again.",
                failure_reason,
            ))
        else:
            _logger.warning(
                "Received Durianpay notification with unhandled status for transaction %s:\n%s",
                self.reference, pprint.pformat(payment_data),
            )
