# -*- coding: utf-8 -*-
# models/partner.py

from odoo import api, fields, models
from odoo.exceptions import UserError

INVALID_ERRORS = (
    "UNREGISTERED",
    "INVALID_ARGUMENT",
)


class NotificationPartner(models.Model):
    _name = "notification.partner"
    _description = "Partner Notification"
    _inherit = [
        "notification.mixin"
    ]

    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        index=True,
        ondelete="restrict",
    )

    email = fields.Char(
        required=True,
        index=True,
    )

    delivery_ids = fields.One2many(
        "notification.delivery",
        'notification_partner_id',
    )

    def _find_active_devices(self):
        devices = self.env["mobile.device"].search([
            ("partner_id", "=", self.partner_id.id),
            ("status", "=", "active"),
        ])

        if not devices:
            raise Exception("No active device.")
        return devices

    def _send_to_devices(self, devices):
        tokens = devices.mapped("fcm_token", )
        response = self.env["amr.firebase.service"].send_to_tokens(
            tokens=tokens,
            title=self.title,
            body=self.body,
            data=self._get_data_payload(),
        )

        return self._process_firebase_response(devices, response, )

    def _process_firebase_response(self, devices, response,):

        success_count = 0
        failed_count = 0

        for device, result in zip(devices, response,):
            self._create_delivery(
                device,
                result,
            )

            if result["success"]:
                success_count += 1
            else:
                failed_count += 1

                self._handle_invalid_token(
                    device,
                    result,
                )

        return {
            "success_count": success_count,
            "failed_count": failed_count,
        }

    def _create_delivery(self, device, result,):
        self.env["notification.delivery"].create({
            "notification_partner_id": self.id,
            "device_id": device.id,
            "state": "sent" if result["success"] else "failed",
            "firebase_message_id": result.get("message_id"),
            "error_message": result.get("error"),
        })

    @api.model
    def _handle_invalid_token(self, device, result,):
        error = result.get("error")
        if error in INVALID_ERRORS:
            device.write({
                "active": False,
            })

    def process_notification(self):
        self.ensure_one()
        try:
            self._mark_processing()
            devices = self._find_active_devices()
            delivery_result = self._send_to_devices(devices, )
            if delivery_result["success_count"]:
                self._mark_sent()
            else:
                raise Exception("No notification delivered.")

        except Exception as ex:
            self._mark_failed(ex)
            raise
    
    def action_process(self):
        try:
            self.process_notification()
        except Exception as ex:
            raise UserError(str(ex))
