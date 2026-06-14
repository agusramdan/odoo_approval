# -*- coding: utf-8 -*-
# models/topic.py
from odoo import fields, models
from ..exceptions.api_exception import ValidationException


class NotificationDelivery(models.Model):
    _name = "notification.delivery"

    notification_id = fields.Many2one(
        "notification.partner",
        required=True,
        ondelete="cascade",
    )

    device_id = fields.Many2one(
        "mobile.device",
        required=True,
        ondelete="restrict",
    )

    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("sent", "Sent"),
            ("failed", "Failed"),
        ],
        default="pending",
        required=True,
    )
    firebase_message_id = fields.Char()

    error_message = fields.Text()
