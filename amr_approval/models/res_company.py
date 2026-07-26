# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models, tools

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    approval_email_layout_xmlid = fields.Many2one(
        'ir.model.data',
        string='Approval Email Layout',
        domain="[('model', '=', 'ir.ui.view')]",
        help="Default email layout used by Approval."
    )
