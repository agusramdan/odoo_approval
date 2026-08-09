# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class ApprovalTask(models.Model):
    _inherit = 'approval.task'

    user_delegation_id = fields.Many2one('user.delegation', compute='_compute_user_delegation')

    @api.depends_context("uid")
    def _compute_user_delegation(self):
        for rec in self:
            user_delegation = rec.get_user_delegation()
            if user_delegation:
                rec.user_delegation_id = user_delegation.id
            else:
                rec.user_delegation_id = None

    def get_user_delegation(self):
        rec = self.ensure_one()
        delegator_ids = rec.get_users().ids
        return self.env.user.get_delegation(delegator_ids, company_id=rec.company_id)
