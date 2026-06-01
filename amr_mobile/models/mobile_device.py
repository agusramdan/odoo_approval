# -*- coding: utf-8 -*-

from odoo import fields, models


class MobileDevice(models.Model):
    _name = "mobile.device"
    _description = "Mobile Device"
    _rec_name = 'device_name'

    active = fields.Boolean(default=True)
    partner_id = fields.Many2one("res.partner", required=True, index=True, )
    user_id = fields.Many2one("res.users", index=True, )
    device_id = fields.Char(required=True, index=True, )
    device_name = fields.Char()
    platform = fields.Selection([
        ("android", "Android"),
        ("ios", "IOS"),
    ])
    fcm_token = fields.Text(required=True)
    registered_at = fields.Datetime(default=fields.Datetime.now,)
    last_seen = fields.Datetime()
    status = fields.Selection(
        [
            ("active", "Active"),
            ("logout", "Logout"),
            ("revoked", "Revoked"),
        ],
        required=True,
        default="active",
        index=True,
    )
    _sql_constraints = [
        (
            "uniq_device",
            "unique(partner_id, device_id)",
            "Device already registered."
        )
    ]
