# -*- coding: utf-8 -*-

import traceback
import json

from odoo import api, fields, models
from odoo.models import BaseModel


class MobileApprovalClient(models.Model):
    _inherit = "mobile.approval.client"

    def dispatch_send(self):
        self.with_delay().send()
