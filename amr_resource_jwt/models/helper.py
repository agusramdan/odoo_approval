# -*- coding: utf-8 -*-

import logging
from odoo import models

_logger = logging.getLogger(__name__)


class ResourceAccessToken(models.AbstractModel):
    _inherit = 'amr.resource.helper'

    # helper will call from Controller
    def validate(self, token):
        try:
            return self.env['auth.jwt.validator'].decode(token)
        except Exception as e:
            return super().validate(token)

    def get_uid(self, payload):
        uid = self.env['auth.jwt.validator']._get_uid(payload)
        if not uid:
            return super().get_uid(payload)
