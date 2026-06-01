# -*- coding: utf-8 -*-

import uuid
from odoo import api, models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    amr_select_issuer = fields.Selection([
        ('web.base.url', 'Web Base URL'),
    ], "Select Issuer", config_parameter='amr_resource.issuer', default='web.base.url')
    amr_resource_issuer = fields.Char(
        "Issuer",
        compute='_compute_resource_issuer'
    )

    amr_select_audience = fields.Selection([
        ('web.base.url', 'Web Base URL'),
        ('database.uuid', 'Database UUID'),
    ], "Select Audience", config_parameter='amr_resource.audience', default='web.base.url')
    amr_resource_audience = fields.Char(
        "Audience",
        compute='_compute_resource_audience'
    )

    module_amr_oidc = fields.Boolean("OIDC")
    module_amr_oidc_client = fields.Boolean("OIDC Client")
    module_amr_token = fields.Boolean("Token Provider")
    module_amr_oauth = fields.Boolean("Client OAuth")
    module_amr_auto_login = fields.Boolean("Auto Login OAuth")
    module_amr_signature = fields.Boolean("Signature")
    # will remove
    module_amr_auth_oauth = fields.Boolean("Auth Oauth")

    @api.depends('amr_select_audience')
    def _compute_resource_issuer(self):
        for record in self:
            if record.amr_select_audience:
                record.amr_resource_issuer = self.env['ir.config_parameter'].sudo().get_param(record.amr_select_issuer,
                                                                                              '')
            else:
                record.amr_resource_issuer = ''

    @api.depends('amr_select_audience')
    def _compute_resource_audience(self):
        for record in self:
            if record.amr_select_audience:
                record.amr_resource_audience = self.env['ir.config_parameter'].sudo().get_param(record.amr_select_audience, '')
            else:
                record.amr_resource_audience = ''
