# -*- coding: utf-8 -*-

import json

from odoo import api, fields, models
from ..exceptions.api_exception import (
    InvalidScopeException, PartnerNotFoundException, ValidationException, DeviceNotFoundException
)


class NotificationService(models.AbstractModel):
    _name = "amr.notification.service"

    @classmethod
    def _required(cls, data, field_name, ):
        value = data.get(field_name)
        if not value:
            raise ValidationException("%s is required" % field_name)

        return value

    @classmethod
    def _get_email(cls, payload):
        email = cls._required(payload, "email", )
        return email.strip().lower()

    @classmethod
    def _get_topic(cls, payload, ):
        topic = payload.get("topic")
        if not topic:
            raise ValidationException(
                "topic is required."
            )

        return topic

    @api.model
    def _find_partner_by_email(self, email, ):

        partner = self.env["res.partner"].sudo().search([("email", "=", email), ], limit=1, )
        if not partner:
            raise PartnerNotFoundException(
                (
                    "Partner with email '%s' "
                    "not found."
                ) % email
            )

        return partner

    @api.model
    def send_notification(self, payload, ):
        self.env['ir.http'].check_scope("notification.send")
        partner = self._find_partner_by_email(
            self._get_email(payload)
        )
        message = self._create_partner_notification(partner, payload, )
        message.dispatch_notification()

        return {
            "message_id": message.id,
            "status": "accepted",
        }

    @api.model
    def send_topic_notification(self, payload, ):
        self.env['ir.http'].check_scope("notification.topic.send", )
        topic = self._get_topic(payload, )
        notification = self._create_topic_notification(topic, payload, )
        notification.dispatch_notification()
        return {
            "notification_id": notification.id,
            "status": "accepted",
        }
