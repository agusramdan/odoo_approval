# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mobile_auto_create_partner = fields.Boolean(config_parameter="amr_mobile.auto_create_partner")
