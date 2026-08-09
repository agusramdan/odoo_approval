
from odoo import models, fields, api


def have_method(obj, method):
    return hasattr(obj, method) and callable(getattr(obj, method))


class ApprovalAuditLog(models.Model):
    _inherit = 'approval.audit.log'

    # delegatee_user_id = fields.Many2one('res.users', string="Acting User")
    # delegator_user_id = fields.Many2one('res.users', string="On Behalf Of")
    # user_delegation_id = fields.Many2one('user.delegation', string="Delegate Rule")

    def create_audit_log(self, **kwargs):
        kw = dict(kwargs)
        user_delegation = kwargs.get('user_delegation')
        if kwargs.get('user_delegation'):
            kw['user_delegation_id'] = int(user_delegation)

        return super(ApprovalAuditLog, self).create_audit_log(**kw)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'user_delegation_id' in vals:
                user_delegate = self.user_delegation_id.browse(vals['user_delegation_id'])
                if not vals.get('delegatee_user_id'):
                    vals['delegatee_user_id'] = user_delegate.delegatee_id.id
                if not vals.get('delegator_user_id'):
                    vals['delegator_user_id'] = user_delegate.delegator_id.id

        return super(ApprovalAuditLog, self).create(vals_list)
