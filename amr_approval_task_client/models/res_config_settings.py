# -*- coding: utf-8 -*-

from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    approval_server_endpoint_id = fields.Many2one(
        'service.endpoint',
        string='Approval Server',
        config_parameter='approval_server_endpoint'
    )
