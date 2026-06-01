# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
import logging

_logger = logging.getLogger(__name__)


class NotificationLog(models.Model):
    _inherit = "notification.log"

    firebase_id = fields.Integer()
    firebase_model = fields.Char()
