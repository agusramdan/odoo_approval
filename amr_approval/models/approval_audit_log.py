# -*- coding: utf-8 -*-

from odoo import models, fields, api
from ..tools.utils import have_method
import logging

_logger = logging.getLogger(__name__)


class ApprovalAuditLog(models.Model):
    _name = 'approval.audit.log'
    _inherit = 'approval.transaction.able.mixin'
    _description = 'Approval Audit Log'
    _order = 'create_date desc'

    name = fields.Char('Name')
    document = fields.Char()
    description = fields.Char()
    company_id = fields.Many2one(
        'res.company'
    )
    user_id = fields.Many2one(
        'res.users',
        "User",
        default=lambda self: self.env.user,
        required=True,
    )
    # jika approval berdasarkan group
    group_name = fields.Char()
    job_position = fields.Char()
    user_delegation_id = fields.Many2one('user.delegation', string="Delegate Rule")

    delegatee_user_id = fields.Many2one('res.users', string="Acting User")
    delegatee_job_position = fields.Char()

    delegator_id = fields.Many2one(
        'res.users',
        "Delegator",
        default=lambda self: self.env.user,
        ondelete='set null',
        help="User who delegated the approval action",
    )
    delegator_job_position = fields.Char()
    action_type = fields.Selection([
        ('approve', 'Approve'),
        ('reject', 'Reject'),
        ('cancel', 'Cancel'),
        ('behalf_approve', 'Behalf Approve'),
        ('behalf_reject', 'Behalf Reject'),
        ('proxy_approve', 'Proxy Approve'),
        ('proxy_reject', 'Proxy Reject'),
    ], required=True)
    requestor_id = fields.Many2one(
        'res.users',
        "Requestor Approval",
    )
    notes = fields.Text(
        'Notes',
        help="Additional notes or comments regarding the action reject"
    )
    create_date = fields.Datetime(
        string='Action Time', readonly=True, default=fields.Datetime.now
    )
    transaction_display_name = fields.Char(
        'Name',
        compute='_compute_transaction_display_name',
        compute_sudo=True,
    )
    notification_template_id = fields.Many2one(
        "notification.template",
        string='Notification',
        ondelete='set null',
    )
    notification_res_id = fields.Integer()

    def _compute_transaction_display_name(self):
        for rec in self:
            obj = rec.get_transaction_object()
            rec.transaction_display_name = obj and obj.display_name or rec.name or rec.display_name

    def get_transaction_object(self):
        if not self.transaction_id or not self.transaction_model_name:
            return False
        """Get the parent document ID if available."""
        # This method should be overridden in child classes if needed
        return self.env[self.transaction_model_name].browse(self.transaction_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'user_delegate_id' in vals:
                user_delegate = self.user_delegate_id.browse(vals['user_delegate_id'])
                if not vals.get('delegatee_user_id'):
                    vals['delegatee_user_id'] = user_delegate.delegatee_id.id
                if not vals.get('delegator_user_id'):
                    vals['delegator_user_id'] = user_delegate.delegator_id.id

        return super(ApprovalAuditLog, self).create(vals_list)

    def create_audit_log(self, **kwargs):
        _field = self._fields
        transaction_model_name = kwargs.get('transaction_object')
        transaction_id = kwargs.get('transaction_id')
        transaction_object = kwargs.get('transaction_object')

        if not transaction_object and transaction_model_name and transaction_id:
            transaction_object = self.env[transaction_model_name].sudo().browse(transaction_id)
        kw = dict(kwargs)
        user_delegate = kwargs.get('user_delegate')
        if user_delegate:
            kw['user_delegate_id'] = int(user_delegate)
            kw['delegatee_user_id'] = user_delegate.delegatee_id.id
            kw['delegator_user_id'] = user_delegate.delegator_id.id

        if transaction_object:
            if 'name' not in kw and have_method(transaction_object, 'get_internal_number'):
                kw['name'] = transaction_object.get_internal_number()

            if not kw.get('document') and have_method(transaction_object, 'get_internal_document'):
                kw['document'] = transaction_object.get_internal_document()

            if not kw.get('description') and have_method(transaction_object, 'get_internal_description'):
                kw['description'] = transaction_object.get_internal_description()

            if not kw.get('requester_id') and have_method(transaction_object, 'get_internal_requester_id'):
                kw['requester_id'] = transaction_object.get_internal_requester_id()

            if 'company_id' not in kw and hasattr(transaction_object, 'company_id'):
                kw['company_id'] = transaction_object.company_id.id

            if not kw.get('transaction_id'):
                kw['transaction_id'] = transaction_object.id

            if not kw.get('transaction_model_name'):
                kw['transaction_model_name'] = transaction_object._name

        create_dict = {key: value for key, value in kw.items() if key in _field}
        ignored_keys = [key for key in kw if key not in _field]
        if ignored_keys:
            _logger.warning("Ignored unknown fields in audit log: %s", ignored_keys)
        return self.create([create_dict])[0]

    def get_approval_line_for_document(self, transaction_model_name, transaction_id, limit=100):
        self.get_approval_audit_log_for_document(transaction_model_name, transaction_id, limit=limit)

    def get_approval_audit_log_for_document(self, transaction_model_name, transaction_id, limit=100):
        approval_line = self.browse()
        candidate = self.search(
            [('transaction_model_name', '=', transaction_model_name), ('transaction_id', '=', transaction_id)],
            limit=limit,
            order='create_date desc'
        )
        for rec in candidate:
            if rec.action_type in ['reject', 'behalf_reject']:
                # stop on first reject
                # asusmi saat terjadi reject maka approval di reset ulang
                break
            approval_line += rec

        if approval_line:
            # reverse
            approval_line = approval_line[::-1]
        return approval_line

    def notification_requestor(self, **kwargs):
        rec = self.ensure_one()
        notification_res_id = rec.notification_res_id or kwargs.get('notification_res_id')
        if rec.notification_template_id and notification_res_id and rec.requestor_id:
            rec.notification_template_id.send_notification_to_users(rec.requestor_id, notification_res_id)
