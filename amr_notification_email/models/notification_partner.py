# -*- coding: utf-8 -*-

import logging

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class NotificationPartner(models.Model):
    _inherit = 'notification.partner'

    _description = 'Notification Partner WhatsApp Extension'

    name = fields.Char(related='partner_id.name', readonly=True)
    send_whatsapp = fields.Boolean(string='Send WhatsApp', default=False)
    whatsapp_phone = fields.Char(string='WhatsApp Phone')
    whatsapp_message = fields.Text(string='WhatsApp Message')

    whatsapp_delivery_ids = fields.One2many(
        comodel_name='notification.whatsapp',
        inverse_name='notification_id',
        string='WhatsApp Deliveries',
    )

    @api.model
    def prepare_notification(self, payload, user=None, **kwargs):
        data_prepare = super(NotificationPartner, self).prepare_notification(
            payload,
            user=user,
            **kwargs,
        )
        data = payload.get('data') or {}
        send_whatsapp = payload.get('send_whatsapp', False) or data.get('send_whatsapp', False)
        whatsapp_message = (
            payload.get('body_whatsapp', False)
            or data.get('body_whatsapp', False)
            or payload.get('message', False)
            or data.get('message', False)
        )

        if send_whatsapp:
            data_prepare['send_whatsapp'] = True
        if whatsapp_message:
            data_prepare['whatsapp_message'] = whatsapp_message

        return data_prepare

    @api.model
    def _get_whatsapp_payload(self, message=None):
        return {
            'to': self.whatsapp_phone,
            'messaging_product': 'whatsapp',
            'type': 'text',
            'text': {'body': message or self.whatsapp_message or ''},
        }

    @api.model
    def send_whatsapp_message(self, message=None):
        self.ensure_one()
        if not self.send_whatsapp:
            raise UserError('WhatsApp delivery is disabled for this notification partner.')
        if not self.whatsapp_phone:
            raise UserError('WhatsApp phone number is required.')
        if not (message or self.whatsapp_message):
            raise UserError('WhatsApp message is required.')

        payload = self._get_whatsapp_payload(message=message)
        try:
            response = requests.post(
                'https://graph.facebook.com/v18.0/000000000000000/messages',
                json=payload,
                timeout=10,
                headers={'Authorization': 'Bearer YOUR_ACCESS_TOKEN'},
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            _logger.exception('WhatsApp API request failed')
            self.env['notification.whatsapp'].create({
                'notification_id': self.id,
                'state': 'failed',
                'error_message': str(exc),
            })
            raise UserError('WhatsApp API request failed: %s' % exc) from exc

        result = response.json() if response.content else {'status': 'ok'}
        self.env['notification.whatsapp'].create({
            'notification_id': self.id,
            'state': 'sent',
            'response_payload': str(result),
        })
        return result

    def action_send_whatsapp(self):
        self.ensure_one()
        self.send_whatsapp_message()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'WhatsApp',
                'message': 'WhatsApp notification sent successfully',
                'sticky': False,
            },
        }
