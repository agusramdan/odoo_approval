# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    notification_auto_create_partner = fields.Boolean(config_parameter="amr.notification.auto_create_partner")
