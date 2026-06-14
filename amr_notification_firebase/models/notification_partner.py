# -*- coding: utf-8 -*-
# models/partner.py

import json

from odoo import api, fields, models
from odoo.exceptions import UserError

INVALID_ERRORS = (
    "UNREGISTERED",
    "INVALID_ARGUMENT",
)


class NotificationPartner(models.Model):
    _inherit = "notification.partner"

    @api.model
    def send_to_tokens(self, tokens):
        return self.env["amr.firebase.service"].send_to_tokens(
            tokens=tokens,
            title=self.title,
            body=self.body,
            image=self.image,
            data=self._get_data_payload(),
        )
