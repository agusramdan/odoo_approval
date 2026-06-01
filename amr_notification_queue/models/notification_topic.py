# -*- coding: utf-8 -*-

from odoo import models


class NotificationTopic(models.Model):
    _inherit = "amr.notification.topic"

    def dispatch_notification(self):

        self.with_delay(channel="notification").process_notification()
