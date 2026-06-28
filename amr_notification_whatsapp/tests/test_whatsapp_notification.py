# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestNotificationWhatsapp(TransactionCase):

    def test_prepare_notification_sets_whatsapp_fields(self):
        partner = self.env['notification.partner'].new({})
        payload = {
            'send_whatsapp': True,
            'body_whatsapp': 'Hello from Odoo',
        }
        result = partner.prepare_notification(payload)
        self.assertTrue(result.get('send_whatsapp'))
        self.assertEqual(result.get('whatsapp_message'), 'Hello from Odoo')

    def test_send_whatsapp_requires_enabled_flag(self):
        partner = self.env['notification.partner'].create({
            'name': 'Test Partner',
            'send_whatsapp': False,
            'whatsapp_phone': '628123456789',
            'whatsapp_message': 'Hello',
        })

        with self.assertRaises(UserError):
            partner.send_whatsapp_message()

    def test_send_whatsapp_requires_phone(self):
        partner = self.env['notification.partner'].create({
            'name': 'Test Partner',
            'send_whatsapp': True,
            'whatsapp_message': 'Hello',
        })

        with self.assertRaises(UserError):
            partner.send_whatsapp_message()

    def test_send_whatsapp_requires_message(self):
        partner = self.env['notification.partner'].create({
            'name': 'Test Partner',
            'send_whatsapp': True,
            'whatsapp_phone': '628123456789',
        })

        with self.assertRaises(UserError):
            partner.send_whatsapp_message()
