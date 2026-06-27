# -*- coding: utf-8 -*-

from odoo import api, fields, models
import json
import traceback


class MobileNotificationClient(models.Model):
    _inherit = "mobile.notification.client"

    def dispatch_send(self):
        self.with_delay().send()
