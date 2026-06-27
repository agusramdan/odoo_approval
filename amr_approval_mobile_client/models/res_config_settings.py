# -*- coding: utf-8 -*-

from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mobile_approval_server_auth_id = fields.Many2one(
        'service.endpoint',
        string='Approval Mobile Server',
        config_parameter='mobile_approval_server_id'
    )
    mobile_notification_server_auth_id = fields.Many2one(
        'service.endpoint',
        string='Notification Mobile Server',
        config_parameter='mobile_notification_server_id'
    )
