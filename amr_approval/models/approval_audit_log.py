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

    name = fields.Char()
    document = fields.Char('Document')
    description = fields.Char('Description')
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
        ('reset', 'Reset'),
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
        string='Execution Time', readonly=True, default=fields.Datetime.now
    )
    request_task_date = fields.Datetime(
        string="Request Task Date",
        readonly=True,
        help="Waktu yang dicatat ketika Approval Task diberikan pada user atau group tertentu.",
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

    # compatible with notification generic requerement

    notification_to_user_id = fields.Many2one(
        'res.users', string='Notification to User',
        compute="_compute_notification_to_user_id", compute_sudo=True,
        help="User who will receive the notification.",
    )
    notification_to_partner_id = fields.Many2one(
        'res.partner', string='Notification to User/Partner',
        compute="_compute_notification_to_user_id", compute_sudo=True,
        help="User who will receive the notification.",
    )

    @api.depends_context('notification_to_user')
    def _compute_notification_to_user_id(self):
        for rec in self:
            notification_to_user = self.env.context.get('notification_to_user', False)
            if notification_to_user:
                rec.notification_to_user_id = notification_to_user.id
                rec.notification_to_partner_id = notification_to_user.partner_id.id
            else:
                rec.notification_to_user_id = False
                rec.notification_to_partner_id = False

    def get_internal_number(self):
        return self.name

    def get_internal_document(self):
        return self.document

    def get_internal_description(self):
        return self.description

    def get_internal_requestor(self):
        return self.requester_id

    def get_internal_url(self):
        return self.url

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
        approval_task = kwargs.get('approval_task')
        if approval_task and approval_task.exists():
            kw['request_task_date'] = approval_task.request_approval_task_date

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

        if not kw.get('user_id'):
            kw['user_id'] = self.env.user.id

        create_dict = {key: value for key, value in kw.items() if key in _field}
        ignored_keys = [key for key in kw if key not in _field]
        if ignored_keys:
            _logger.warning("Ignored unknown fields in audit log: %s", ignored_keys)
        return self.sudo().create([create_dict])[0]

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

    def create_approval_audit_log(self, **kwargs):
        transaction_object = kwargs.get('transaction_object')
        kw = dict(kwargs)
        if transaction_object and isinstance(transaction_object, models.BaseModel):
            if have_method(transaction_object, "create_approval_log"):
                return transaction_object.create_approval_log(**kw)
            kw.update(
                transaction_id=transaction_object.id,
                transaction_model_name=transaction_object._name,
            )
        return self.env['approval.audit.log'].create_audit_log(**kw)

    def create_approval_audit_log_approved(self, **kwargs):
        kw = dict(kwargs)
        kw['action_type'] = 'approve'
        kw.setdefault('name', 'Approve')
        return self.create_approval_audit_log(**kw)

    def create_approval_audit_log_rejected(self, **kwargs):
        kw = dict(kwargs)
        kw['action_type'] = 'reject'
        kw.setdefault('name', 'Reject')
        return self.create_approval_audit_log(**kw)

    def create_approval_audit_log_canceled(self, **kwargs):
        kw = dict(kwargs)
        kw['action_type'] = 'cancel'
        kw.setdefault('name', 'Cancel')
        return self.create_approval_audit_log(**kw)

    def create_approval_audit_log_reset(self, **kwargs):
        kw = dict(kwargs)
        kw['action_type'] = 'reset'
        kw.setdefault('name', 'Reset')
        return self.create_approval_audit_log(**kw)

    def get_res_id_for_notification(self, notification_approval, **kwargs):
        self.ensure_one()
        res_id = None
        model_name = None
        if notification_approval:
            model_name = notification_approval.model
            if model_name:
                if self.transaction_model_name == model_name:
                    res_id = self.transaction_id
                elif self._name == model_name:
                    res_id = self.id

        return res_id, model_name

    def send_notification(self, **kwargs):
        self.ensure_one()
        notification_log = None
        try:
            notification_approval = kwargs.get("notification_approval")
            if not notification_approval:
                return notification_log

            kwargs['approval_audit_log_id'] = self.id
            if notification_approval:
                res_id, model_name = self.get_res_id_for_notification(notification_approval, **kwargs)
                if res_id:
                    users = self.get_users_for_notification(**kwargs)
                    if self.user_id:
                        notification_approval = notification_approval.with_user(self.user_id)
                    kwargs.pop('users', None)
                    kwargs.pop('res_id', None)
                    notification_log = notification_approval.send_notification_to_users(
                        users, res_id, **kwargs
                    )
        except Exception:
            _logger.exception("skip error")
        finally:
            _logger.info("Send Notification done")
        return notification_log
