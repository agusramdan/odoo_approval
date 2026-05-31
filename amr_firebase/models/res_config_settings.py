# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    firebase_credentials_json = fields.Boolean(config_parameter="amr_firebase.firebase_credentials_json")
