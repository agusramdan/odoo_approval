# -*- coding: utf-8 -*-
# models/partner.py

import logging
import json

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

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

    notification_type = fields.Selection([
        ("approval", "Approval"),
        ("info", "Info"),
    ], default="approval", index=True)

    user_id = fields.Many2one(
        "res.users",
        index=True,
        ondelete="restrict",
    )

    partner_id = fields.Many2one(
        "res.partner",
        index=True,
        ondelete="restrict",
    )

    delivery_ids = fields.One2many(
        "notification.delivery",
        'notification_id',
    )
    source_application = fields.Char()
    source_model = fields.Char()
    source_res_id = fields.Integer()
    source_url = fields.Char()

    @api.model
    def prepare_notification(self, payload, user=None, **kwargs):
        data_prepare = super(NotificationPartner, self).prepare_notification(payload)
        data = payload.get('data') or {}
        data_prepare['source_application'] = payload.get('source_application') or data.get('source_application')
        data_prepare['source_model'] = payload.get('source_model') or data.get('source_model')
        data_prepare['source_res_id'] = payload.get('source_res_id') or data.get('source_res_id')
        data_prepare['source_url'] = payload.get('source_url') or data.get('source_url')
        notification_to_user = payload.get('email') or data.get('notification_to_user')
        mobile_phone = payload.get('phone')
        to_user = user
        to_partner = None
        phones = None
        if not to_user and notification_to_user:
            to_user = self.env['res.users'].search(
                ['|', ('partner_id.email', '=', notification_to_user), ('login', '=', notification_to_user)], limit=1)

        if not to_user and mobile_phone and 'hr.employee' in self.env:
            phones = [mobile_phone]
            if mobile_phone.startswith("62"):
                phones.append("0" + mobile_phone[2:])
            elif mobile_phone.startswith("0"):
                phones.append("62" + mobile_phone[1:])
            _logger.info("Searching for phones: %s", phones)
            employee = self.env['hr.employee'].search([('mobile_phone', 'in', phones)], limit=1)
            to_user = employee.user_id

        if to_user:
            to_partner = to_user.partner_id
            data_prepare['user_id'] = to_user.id

        if not to_partner and notification_to_user:
            to_partner = self.env['res.partner'].search([('email', '=', notification_to_user)], limit=1)

        if not to_partner and phones:
            to_partner = self.env['res.partner'].search([('phone', 'in', phones)], limit=1)

        if to_partner:
            data_prepare['partner_id'] = to_partner.id
        return data_prepare

    def _find_active_devices(self):
        devices = self.env["mobile.device"].search([
            ("partner_id", "=", self.partner_id.id),
            ("status", "=", "active"),
        ])

        if not devices:
            raise Exception("No active device.")
        return devices

    def send_to_devices(self, devices):
        tokens = devices.mapped("fcm_token", )

        response = self.send_to_tokens(
            tokens=tokens,
        )

        return self._process_firebase_response(devices, response, )

    @api.model
    def send_to_tokens(self, tokens):
        return [{} for t in tokens]

    def _process_firebase_response(self, devices, response, ):

        success_count = 0
        failed_count = 0

        for device, result in zip(devices, response, ):
            self._create_delivery(device, result, )
            if result["success"]:
                success_count += 1
            else:
                failed_count += 1
                self.handle_invalid_token(device, result, )
        return {
            "success_count": success_count,
            "failed_count": failed_count,
        }

    def _create_delivery(self, device, result, ):
        self.env["notification.delivery"].create({
            "notification_id": self.id,
            "device_id": device.id,
            "state": "sent" if result["success"] else "failed",
            "firebase_message_id": result.get("message_id"),
            "error_message": result.get("error"),
        })

    @api.model
    def handle_invalid_token(self, device, result, ):
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
            delivery_result = self.send_to_devices(devices, )
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

    def action_approval_show(self):
        self.ensure_one()
        if self.notification_type != "approval":
            raise UserError("Notification is not an approval type.")

        if not self.source_model or not self.source_res_id:
            raise UserError("Source model atau Source ID kosong.")

        # Menyusun URL rute internal standar Odoo 13 untuk Form View
        if self.source_url:
            odoo_internal_url = self.source_url
        else:
            odoo_internal_url = "%s/web#id=%s&model=%s&view_type=form" % (
                self.get_base_url(), self.source_res_id, self.source_model
            )

        # Kembalikan sebagai tipe act_url murni
        return {
            "type": "ir.actions.act_url",
            "url": odoo_internal_url,
            "target": "self",  # "self" agar berpindah di tab yang sama, "new" jika ingin tab baru
        }
