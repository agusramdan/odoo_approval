# -*- coding: utf-8 -*-
# models/message_mixin.py
import json

from odoo import fields, models


class NotificationMessageMixin(models.AbstractModel):
    _name = "notification.mixin"
    _description = "Notification Message Mixin"

    source = fields.Char(required=True, index=True,)
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

    def _get_data_payload(self):
        if not self.data_json:
            return {}

        return json.loads(
            self.data_json
        )

    def _mark_processing(self):
        self.write({
            "state": "processing",
        })

    def _mark_sent(self):
        self.write({
            "state": "sent",
            "processed_at":
                fields.Datetime.now(),
        })

    def _mark_failed(self, ex, ):
        self.write({
            "state": "failed",
            "error_message": str(ex),
            "retry_count":
                self.retry_count + 1,
        })

    def process_notification(self):
        raise NotImplementedError(
            "process_notification must be implemented"
        )

    def dispatch_notification(self):
        self.process_notification()
