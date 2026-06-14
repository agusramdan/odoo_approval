# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    firebase_credentials_id = fields.Many2one(
        "service.credential",
        config_parameter="amr_notification_firebase.credentials_id"
    )
