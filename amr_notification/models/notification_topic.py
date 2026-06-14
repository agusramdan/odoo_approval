# -*- coding: utf-8 -*-
# models/topic.py
import json

from odoo import api, fields, models
from ..exceptions.api_exception import ValidationException


class NotificationTopic(models.Model):
    _name = "notification.topic"
    _description = "Topic Notification"
    _inherit = [
        "notification.mixin",
    ]

    topic = fields.Char()
    condition = fields.Char()

    def _validate_topic(self):
        if not self.topic:
            raise ValidationException(
                "Topic is required."
            )

    def process_notification(self):
        self.ensure_one()
        try:
            self._mark_processing()
            self.send_to_topic()
            self._mark_sent()
        except Exception as ex:
            self._mark_failed(ex)
            raise

    def send_to_topic(self):
        pass

    @api.model
    def prepare_topic(self, payload):
        payload = dict(payload)
        notification = payload.pop("notification", {})
        data = payload.pop("data", {})
        title = payload.pop("title", "") or notification.get("title", "")
        body = payload.pop("body", "") or notification.get("body", "")
        payload.update(data)
        return {
            "title": title,
            "body": body,
            'data_json': json.dumps(payload),
        }
