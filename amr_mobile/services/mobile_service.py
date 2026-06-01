# -*- coding: utf-8 -*-

import json

from odoo import api, fields, models
from ..exceptions.api_exception import (
    InvalidScopeException, PartnerNotFoundException, ValidationException, DeviceNotFoundException
)


class M(models.Model):
    _name = 'amr.user.public.key'


class MobileService(models.AbstractModel):
    _name = "mobile.service"

    @classmethod
    def _required(cls, data, field_name, ):
        value = data.get(field_name)
        if not value:
            raise ValidationException("%s is required" % field_name)

        return value

    @classmethod
    def _check_scope(cls, jwt_payload, required_scope, ):

        scopes = jwt_payload.get("scope", [])
        if isinstance(scopes, str):
            scopes = scopes.split()

        if required_scope not in scopes:
            raise InvalidScopeException(required_scope)

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
    def _get_partner(self, data, raise_not_found=True):
        notification_code = data.get("notification_code")
        email = data.get("email")
        partner = None

        if notification_code:
            partner = self.env["res.partner"].sudo().search(
                [("notification_code", "=", notification_code)], limit=1,
            )

        if not partner and email:
            partner = self.env["res.partner"].sudo().search(
                [("email", "=", email)], limit=1,
            )

        if partner:
            return partner
        elif raise_not_found:
            raise PartnerNotFoundException()

    @api.model
    def _get_or_create_partner(self, data):
        if not self.env.user.is_user_machine():
            # register user sendiri bukan machine/mobile app
            return self.env.user.partner_id

        partner = self._get_partner(self, data, raise_not_found=False)

        if partner:
            return partner

        return self._handle_partner_not_found(data)

    @api.model
    def _handle_partner_not_found(self, data=None, ):

        mode = (
            self.env["ir.config_parameter"].sudo().get_param(
                "amr_mobile.partner_registration_mode",
                "reject",
            )
        )

        if mode == "reject":
            raise PartnerNotFoundException()

        notification_code = data.get("notification_code")
        email = data.get("email")

        return self.env["res.partner"].sudo().create({
            "name": notification_code or email,
            "notification_code": notification_code,
            "email": email,
            "is_notification_client": True,
        })

    @api.model
    def _create_partner_notification(self, partner, payload, jwt_payload, ):
        source = (
                jwt_payload.get("client_id")
                or jwt_payload.get("iss")
                or "unknown"
        )

        return self.env["amr.notification.partner"].sudo().create({
            "partner_id": partner.id,
            "email": partner.email,
            "source": source,
            "raw_payload": json.dumps(payload),
            "state": "pending",
        })

    @api.model
    def register_device(self, data):
        if self.env.user.is_user_machine():
            self.env['ir.http'].check_scope("mobile.device.register", )
            partner = self._get_partner(data)
            user_id = None
        else:
            # register user sendiri bukan machine/mobile app
            partner = self.env.user.partner_id
            user_id = self.env.uid
        device_id = self._required(data, "device_id", )
        fcm_token = self._required(data, "fcm_token", )
        platform = data.get("platform")
        device_name = data.get("device_name")

        device = self.env["mobile.device"].sudo().search(
            [
                ("partner_id", "=", partner.id),
                ("device_id", "=", device_id),
            ],
            limit=1,
        )

        vals = {
            "partner_id": partner.id,
            "user_id": user_id,
            "device_id": device_id,
            "device_name": device_name,
            "platform": platform,
            "fcm_token": fcm_token,
            "status": "active",
            "active": True,
            "last_seen": fields.Datetime.now(),
        }

        if device:
            device.write(vals)
        else:
            device = self.env["mobile.device"].sudo().create(vals)

        return {
            "id": device.id,
            "device_id": device.device_id,
            "registered": True,
        }

    @api.model
    def logout_device(self, data, ):
        if self.env.user.is_user_machine():
            self.env['ir.http'].check_scope("mobile.device.logout", )
            partner = self._get_or_create_partner(data)
            # user_id = None
        else:
            # register user sendiri bukan machine/mobile app
            partner = self.env.user.partner_id
            # user_id = self.env.uid
        device_id = self._required(data, "device_id", )

        device = self.env["mobile.device"].sudo().search(
            [
                ("partner_id", "=", partner.id),
                ("device_id", "=", device_id),
            ],
            limit=1,
        )

        if not device:
            raise DeviceNotFoundException()

        device.write({
            "status": "logout",
            "last_seen": fields.Datetime.now(),
        })

        return {
            "device_id": device.device_id,
            "status": device.status,
        }

    @api.model
    def revoke_device(self, data, ):

        self.env["ir.http"].check_scope("mobile.device.revoke", )

        partner = self._get_or_create_partner(data, )

        device_id = self._required(data, "device_id", )

        device = self.env["mobile.device"].sudo().search(
            [
                ("partner_id", "=", partner.id),
                ("device_id", "=", device_id),
            ],
            limit=1,
        )

        if not device:
            raise DeviceNotFoundException()

        device.write({
            "status": "revoked",
            "last_seen": fields.Datetime.now(),
        })

        return {
            "device_id": device.device_id,
            "status": device.status,
        }

    def revoke_all_device(self, jwt_payload, data, ):

        self.env['ir.http'].check_scope("notification.device.logout", )
        partner = self._get_or_create_partner(jwt_payload, )
        device_id = self._required(data, "device_id", )
        device = self.env["mobile.device"].sudo().search(
            [
                ("partner_id", "=", partner.id),
                ("device_id", "=", device_id),
            ],
            limit=1,
        )

        if not device:
            raise DeviceNotFoundException()

        device.write({
            "status": "logout",
            "last_seen": fields.Datetime.now(),
        })

        return {
            "device_id": device.device_id,
            "status": device.status,
        }
