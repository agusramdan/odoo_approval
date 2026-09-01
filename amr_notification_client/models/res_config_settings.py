# -*- coding: utf-8 -*-

from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    notification_server_endpoint_id = fields.Many2one(
        'service.endpoint',
        string='Notification Server',
        config_parameter='notification_server_endpoint'
    )
