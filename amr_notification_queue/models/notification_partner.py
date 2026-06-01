# -*- coding: utf-8 -*-
# models/partner.py

from odoo import api, fields, models


class NotificationPartner(models.Model):
    _inherit = "amr.notification.partner"

    def dispatch_notification(self):

        self.with_delay(channel="notification").process_notification()
