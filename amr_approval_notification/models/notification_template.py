# -*- coding: utf-8 -*-

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class NotificationTemplate(models.Model):
    _inherit = "notification.template"

    @api.model
    def send_notification_firebase(self, notification_to_user, payload, notif_log, **kwargs):
        if "notification.service" in self.env:
            notification = self.env["notification.service"].sudo().create_notification(
                payload, user=notification_to_user
            )
            notification.dispatch_notification()
            notif_log['notification_id'] = notification.id
            notif_log['notification_model'] = notification._name
