# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class ApprovalTaskLineMixin(models.AbstractModel):
    _inherit = "approval.task.line.mixin"
    _description = "Approval Task Line Integration Mixin"

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
        company = None
        if 'company_id' in self._fields:
            company = rec.company_id
        return self.env.user.get_delegation(delegator_ids, company_id=company)

    def do_approve(self, **kwargs):
        rec = self.ensure_one()
        user_delegation = kwargs.get('user_delegation') or rec.get_user_delegation()
        if user_delegation:
            self.write({'user_delegation_id':user_delegation.id})
            kw = dict(kwargs)
            kw['user_delegation'] = user_delegation
        else:
            kw = kwargs
        return super(ApprovalTaskLineMixin, self).do_approve(**kw)

    def do_reject(self, reason=None, **kwargs):
        rec = self.ensure_one()
        user_delegation = kwargs.get('user_delegation') or rec.get_user_delegation()
        if user_delegation:
            self.write({'user_delegation_id': user_delegation.id})
            kw = dict(kwargs)
            kw['user_delegation'] = user_delegation
        else:
            kw = kwargs
        return super(ApprovalTaskLineMixin,self).do_reject( reason=reason, **kw)
