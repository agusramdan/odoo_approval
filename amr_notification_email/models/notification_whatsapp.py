# -*- coding: utf-8 -*-

from odoo import fields, models


class NotificationWhatsapp(models.Model):
    _name = 'notification.whatsapp'
    _description = 'WhatsApp Delivery Log'

    notification_id = fields.Many2one(
        comodel_name='notification.partner',
        string='Notification',
        ondelete='cascade',
    )
    state = fields.Selection(
        [('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed')],
        default='pending',
        required=True,
    )
    response_payload = fields.Text(string='Response Payload')
    error_message = fields.Text(string='Error Message')
