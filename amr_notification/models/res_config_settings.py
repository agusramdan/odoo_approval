# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    notification_auto_create_partner = fields.Boolean(config_parameter="amr.notification.auto_create_partner")
    module_amr_notification_firebase = fields.Boolean("Notification Firebase")
    module_amr_notification_whatsapp = fields.Boolean("Notification Whatsapp")
    module_amr_notification_telegram = fields.Boolean("Notification Telegram")
