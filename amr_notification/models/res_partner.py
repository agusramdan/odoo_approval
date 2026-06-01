# -*- coding: utf-8 -*-

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_notification_client = fields.Boolean(
        string="Notification Client"
    )

    notification_code = fields.Char(
        required=False,
        index=True,
        copy=False,
    )

    active_notification = fields.Boolean(
        default=True
    )

    _sql_constraints = [
        (
            "notification_code_unique",
            "unique(notification_code)",
            "Notification code must be unique."
        )
    ]
