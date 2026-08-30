# -*- coding: utf-8 -*-

import logging

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class NotificationPartner(models.Model):
    _inherit = 'notification.partner'

    def notification_bus_dict(self):
        self.ensure_one()

        return {
            'id': self.id,
            'title': self.title,
            'message': self.body,
            'is_read': self.is_read,
            'create_date': self.create_date,
            'notification_type': self.notification_type,
            'source_model': self.source_model,
            'source_res_id': self.source_res_id,
        }

    def send_to_bus(self):
        record = self.ensure_one()
        bus = self.env["bus.bus"]
        # data_payload = self._get_data_payload()
        if self.user_id:
            notification_payload = self.notification_bus_dict()
            target_user_channel = 'notification_bus_user_%s' % record.user_id.id
            bus.sendone(
                target_user_channel,
                notification_payload,
            )
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Bus',
                    'message': 'Notification sent successfully',
                    'sticky': False,
                },
            }

    def action_send_bus(self):
        self.ensure_one()
        return self.send_to_bus()

    @api.model_create_multi
    @api.returns('self', lambda value: value.id)
    def create(self, vals_list):
        records = super(NotificationPartner, self).create(vals_list)
        for record in records:
            record.send_to_bus()
        return records
