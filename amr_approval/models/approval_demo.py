# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.Logger(__name__)


class ApprovalDemo(models.Model):
    _name = 'approval.demo'
    _inherit = ['approval.report.mixin', 'mail.thread']
    _description = 'Approval Demo and Simulation'
    _order = 'name'

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        'res.company', string='Company', default=lambda self: self.env.company
    )
    user_id = fields.Many2one(
        'res.users', string='Requester', default=lambda self: self.env.user
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('waiting_approval', 'Waiting Approval'), ('approved', 'Approved'),
         ('rejected', 'Rejected'), ('cancel', 'Cancel'), ('error', 'Error'), ],
        default='draft',
        string='State',
    )
    description = fields.Text()

    def action_print(self):
        return self.env.ref('amr_approval.action_report_approval_demo_form').report_action(self)
