# -*- coding: utf-8 -*-
# models/topic.py
from odoo import api, fields, models
from ..exceptions.api_exception import ValidationException

class NotificationMessageMixin(models.AbstractModel):
    _name = "notification.mixin"
    _description = "Notification Message Mixin"

    title = fields.Char(required=True,)
    body = fields.Text()
    data_json = fields.Text()
    raw_payload = fields.Text(required=True,)
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("sent", "Sent"),
            ("failed", "Failed"),
        ],
        default="pending",
        required=True,
        index=True,
    )
    processed_at = fields.Datetime()
    error_message = fields.Text()
    retry_count = fields.Integer(
        default=0,
    )
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
