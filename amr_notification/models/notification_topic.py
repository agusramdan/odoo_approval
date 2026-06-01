# -*- coding: utf-8 -*-
# models/topic.py
from odoo import fields, models
from ..exceptions.api_exception import ValidationException


class NotificationTopic(models.Model):
    _name = "notification.topic"
    _description = "Topic Notification"
    _inherit = [
        "notification.mixin",
    ]

    topic = fields.Char(
        required=True,
        index=True,
    )

    def _validate_topic(self):
        if not self.topic:
            raise ValidationException(
                "Topic is required."
            )

    def process_notification(self):
        self.ensure_one()
        try:
            self._mark_processing()
            self._send_to_firebase_topic()
            self._mark_sent()
        except Exception as ex:
            self._mark_failed(ex)
            raise

    def _send_to_firebase_topic(self):
        self.env["amr.firebase.service"].send_to_topic(
            topic=self.topic,
            title=self.title,
            body=self.body,
            data=self._get_data_payload(),
        )
