# -*- coding: utf-8 -*-

from odoo import models

import logging

_logger = logging.getLogger(__name__)


class NotificationTemplate(models.Model):
    _inherit = "notification.template"

    def get_mobile_notification_client(self):
        return self.env['mobile.notification.client']

    def send_notification_mobile(self, notification_to_user, payload, notif_log, **kwargs):
        mobile_notification_client = self.get_mobile_notification_client()
        notif = mobile_notification_client.create_payload(**payload)
        notif.process()
        if notif and notif_log is not None:
            notif_log['mobile_id'] = notif.id
            notif_log['mobile_model'] = notif._name
        notif.dispatch_send()
        return notif
