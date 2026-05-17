# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..tools.utils import have_method, safe_call_method

_logger = logging.getLogger(__name__)


class ApprovalTaskLineMixin(models.AbstractModel):
    _name = "approval.task.line.mixin"
    _description = "Approval Task Line Integration Mixin"

    transaction_id = fields.Integer()
    transaction_model_name = fields.Char()
    approval_instance_id = fields.Many2one(
        'approval.instance',
        ondelete='set null',
    )
    approval_task_id = fields.Many2one(
        'approval.task',
        ondelete='set null',
    )
    reject_to_method = fields.Selection([
        ('legacy', "Legacy"),
        ('to_requestor', "To Requestor"),
        ('to_previous', "To Previous"),
        ('to_task_line', "To Task Line"),
    ], default='legacy', readonly=True)
    requester_id = fields.Many2one(
        'res.users', 'Requester',
        default=lambda self: self.env.user,
        help="User who requested the approval."
    )
    user_execution_id = fields.Many2one(
        'res.users', 'User Execution',
        help="User who executed approval (Approve/Reject)the transaction"
    )
    date_execution = fields.Datetime('Date Execution')
    reject_reason = fields.Text('Reject Reason')
    sign_title = fields.Char("Sign Title")
    approval_user_ids = fields.Many2many(
        'res.users', compute='_compute_approval_user_ids', compute_sudo=True
    )
    user_delegation_id = fields.Many2one('user.delegation', compute='_compute_user_delegation')
    matrix_rule_line_id = fields.Many2one('approval.matrix.rule.line')
    reject_to_matrix_rule_line_id = fields.Many2one('approval.matrix.rule.line')
    reject_to_task_line_id = fields.Many2one('approval.task.line.mixin')

    def _compute_approval_user_ids(self):
        for rec in self:
            rec.approval_user_ids = rec.get_users_for_approval()

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
        if 'company_id' in self._fields:
            company = rec.company_id
        else:
            company = None
        return self.env.user.get_delegation(delegator_ids, company_id=company)

    def get_reject_to_task_line(self):
        return self.reject_to_task_line_id

    def get_approval_start_task(self, start_task):
        """
        Get list approval from start_task to this object
        """
        end_task = self.ensure_one()
        approve_task_line_between = self.browse()
        approval_task_line = self.get_all_approval_task_line()
        found_start = not start_task
        for task in approval_task_line:
            if found_start:
                if end_task.id == task.id:
                    break
                approve_task_line_between |= task
            elif task.id == start_task.id:
                found_start = True

        return approve_task_line_between

    def get_approval_instance(self):
        if self:
            transaction_model_name = self[0].transaction_model_name
            transaction_id = self[0].transaction_id
            return self.env['approval.instance'].search(
                [('transaction_id', '=', transaction_id), ('transaction_model_name', '=', transaction_model_name)],
                limit=1)
        return self.env['approval.instance'].browse()

    def get_all_approval_task_line(self, transaction_id=None, transaction_model_name=None):
        for rec in self:
            if rec.transaction_id and rec.transaction_model_name:
                transaction_id = rec.transaction_id
                transaction_model_name = rec.transaction_model_name
                break

        if not transaction_model_name or not transaction_id:
            raise UserError(" Transaction not set ")
        return self.search(
            [('transaction_id', '=', transaction_id), ('transaction_model_name', '=', transaction_model_name)])

    def get_previous_approval_task_line(self, transaction_id=None, transaction_model_name=None):
        end_task = self.ensure_one()
        previous = self.browse()
        approval_task_line = self.get_all_approval_task_line()
        for task in approval_task_line:
            if end_task.id == task.id:
                break
            previous = task
        return previous

    def get_last_approval_task_line(self, transaction_id=None, transaction_model_name=None):
        return self.search(
            [('transaction_id', '=', transaction_id), ('transaction_model_name', '=', transaction_model_name)],
            order='id desc', limit=1)

    def get_next_approval_task_line(self, transaction_id=None, transaction_model_name=None):
        if not transaction_id or not transaction_model_name:
            if self:
                transaction_model_name = transaction_model_name or self[0].transaction_model_name
                transaction_id = transaction_id or self[0].transaction_id
            else:
                return self.browse()
        domain = [('transaction_id', '=', transaction_id), ('transaction_model_name', '=', transaction_model_name)]
        if have_method(self, "domain_waiting_status"):
            domain.extend(self.domain_waiting_status() or [])
        result = self.search(domain, limit=1)
        return result

    def register_approval_task(self, **kwargs):

        return self.register_to_approval_task(**kwargs)

    def register_to_approval_task(self, **kwargs):
        self.ensure_one()
        if have_method(self, "prepare_approval_task_dict"):
            kw = self.prepare_approval_task_dict()
            kw.update(kwargs)
        else:
            kw = dict(kwargs)

        transaction_object = kw.get('transaction_object') or safe_call_method(self, 'get_transaction_object', )
        if transaction_object:
            if have_method(transaction_object, 'prepare_approval_task_dict'):
                update = safe_call_method(transaction_object, 'prepare_approval_task_dict', kwargs=kw)
                update and kw.update(update)
            kw['transaction_id'] = transaction_object.id
            kw['transaction_model_name'] = transaction_object._name

        transaction_id = kw.pop('transaction_id')
        transaction_model_name = kw.pop('transaction_model_name')

        self.approval_task_id = self.env['approval.task'].approval_setup(transaction_id, transaction_model_name, **kw)

        return self.approval_task_id

    def _create_approval_audit_log(self, **kwargs):
        if self.env.context.get('__skip_create_approval_audit_log'):
            return None

        self.ensure_one()
        transaction_object = kwargs.get('transaction_object')
        kw = dict(kwargs)
        if transaction_object:
            if have_method(transaction_object, "create_approval_log"):
                return transaction_object.create_approval_log(**kw)
            kw.update(
                transaction_id=transaction_object.id,
                transaction_model_name=transaction_object._name
            )
        return self.env['approval.audit.log'].create_audit_log(**kw)

    def create_approval_audit_log_approved(self, **kwargs):
        kw = dict(kwargs)
        kw['action_type'] = 'approve'
        return self._create_approval_audit_log(**kw)

    def create_approval_audit_log_rejected(self, **kwargs):
        kw = dict(kwargs)
        kw['action_type'] = 'reject'
        return self._create_approval_audit_log(**kw)

    def send_approval_notification(self, **kwargs):
        pass

    def send_rejected_notification(self, **kwargs):
        pass

    def send_approved_notification(self, **kwargs):
        pass

    def set_approved_status(self, **kwargs):
        if have_method(self, "set_approve_state"):
            self.set_approve_state()
        self.write({
            'user_execution_id': self.env.uid,
            'date_execution': fields.Datetime.now(),
        })

    def set_rejected_status(self, **kwargs):
        if have_method(self, "set_reject_state"):
            self.set_reject_state()
        self.write({
            'user_execution_id': self.env.uid,
            'date_execution': fields.Datetime.now(),
            'reject_reason': kwargs.get('reject_reason') or kwargs.get('reason') or self.env.context.get(
                '__reject_reason')
        })

    def set_waiting_status(self, **kwargs):
        if have_method(self, "set_waiting_approval_state"):
            self.set_waiting_approval_state()
        self.write({
            'user_execution_id': False,
            'date_execution': False,
            'reject_reason': False,
        })

    def action_approve(self, **kwargs):
        rec = self.ensure_one()
        rec.do_approve(**kwargs)

    def action_reject(self, **kwargs):
        context = dict(self.env.context)
        model_name = context.get('model_name')
        model_res_id = context.get('model_res_id')
        approval_instance = kwargs.get('approval_instance')
        transaction_object = kwargs.get('transaction_object')
        if approval_instance and isinstance(approval_instance, models.Model):
            model_name = approval_instance._name
            model_res_id = approval_instance.id
        elif transaction_object and isinstance(transaction_object, models.Model):
            model_name = transaction_object._name
            model_res_id = transaction_object.id
        if not model_name or not model_res_id and self:
            model_name = self._name
            model_res_id = self.ids[0]
        if model_name and model_res_id:
            context.update({
                'active_model': model_name,
                'active_id': model_res_id,
                'model_name': model_name,
                'model_res_id': model_res_id,
            })
        _logger.info(" model_name %s , model_res_id %s ", model_name, model_res_id)
        return {
            'name': 'Reject Message',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'popup.reject.message.wizard',
            'target': 'new',
            'context': context,
        }

    def do_approve(self, **kwargs):
        rec = self.ensure_one()
        if not rec.access_approval:
            raise UserError("User not allow to approve")
        kw = dict(kwargs)
        if 'transaction_object' not in kw:
            kw['transaction_object'] = self.get_transaction_object()
        kw['approval_task_line'] = rec
        if not kwargs.get('user_delegation'):
            kw['user_delegation'] = rec.get_user_delegation()
        rec.before_approve(**kw)
        rec.with_context(__skip_create_approval_audit_log=True).set_approved_status(**kw)
        rec.create_approval_audit_log_approved(**kw)
        rec.after_approve(**kw)

    def before_approve(self, **kwargs):
        rec = self
        kw = dict(kwargs)
        kw['approval_task_line'] = rec
        approval_instance = kwargs.get('approval_instance') or rec.get_approval_instance()
        approval_instance and approval_instance.before_approve(**kw)

    def after_approve(self, **kwargs):
        rec = self
        kw = dict(kwargs)
        approval_task_line_next = rec.get_next_approval_task_line()
        kw['approval_task_line'] = rec
        kw['approval_task_line_next'] = approval_task_line_next
        kw['is_approval_done'] = not approval_task_line_next
        approval_instance = kwargs.get('approval_instance') or rec.get_approval_instance()
        if approval_instance:
            approval_instance.after_approve(**kw)
        else:
            transaction_object = kw.get('transaction_object') or rec.get_transaction_object()
            if have_method(transaction_object, 'event_after_approve'):
                safe_call_method(transaction_object, 'event_after_approve')

    def reject_method_legacy(self, reason=None, **kwargs):
        raise NotImplemented
        # return approval_task_line_next, approval_task_line_between

    def do_reject(self, reason=None, **kwargs):
        self.ensure_one()
        kw = dict(kwargs)
        if not self.access_approval:
            raise UserError("User not allow to reject")
        kw['reason'] = reason
        if 'transaction_object' not in kw:
            kw['transaction_object'] = self.get_transaction_object()
        if not kwargs.get('user_delegation'):
            kw['user_delegation'] = self.get_user_delegation()
        self.before_reject(**kwargs)
        is_approval_done = False
        approval_task_line_next = None
        approval_task_line_between = self.browse()
        if self.reject_to_method == 'to_requestor':
            is_approval_done = True
            approval_task_line_between = self.get_approval_start_task(None)
        else:
            if self.reject_to_method == 'to_task_line':
                approval_task_line_next = self.get_reject_to_task_line()
                approval_task_line_between = self.get_approval_start_task(approval_task_line_next)
            elif self.reject_to_method == 'to_previous':
                approval_task_line_next = self.get_previous_approval_task_line()
            elif self.reject_to_method == 'legacy':
                approval_task_line_next, approval_task_line_between = self.reject_method_legacy(reason, **kwargs)
            else:
                approval_task_line_next = kwargs.get('approval_task_line_next')
                approval_task_line_between = kwargs.get('approve_task_line_between') or self.get_approval_start_task(
                    approval_task_line_next)
            is_approval_done = not approval_task_line_next
        if is_approval_done:
            kw['is_approval_done'] = True
            kw['is_rejected'] = True
        else:
            kw['approval_task_line_next'] = approval_task_line_next
        kw['approve_task_task_between'] = approval_task_line_between
        kw['approve_task_line'] = kw['approve_task_line_reject'] = self
        self.with_context(__skip_create_approval_audit_log=True).set_rejected_status(**kw)
        self.create_approval_audit_log_rejected(**kw)
        self.after_reject(**kw)
        if not is_approval_done and approval_task_line_next:
            approval_task_line_next.set_waiting_status(**kw)
            if approval_task_line_between:
                approval_task_line_between.set_waiting_status(**kw)

    def before_reject(self, **kwargs):
        rec = self
        kw = dict(kwargs)
        kw['approval_task_line'] = rec
        approval_instance = kwargs.get('approval_instance') or rec.get_approval_instance()
        approval_instance and approval_instance.before_reject(**kw)

    def after_reject(self, **kwargs):
        rec = self
        kw = dict(kwargs)
        kw['approval_task_line'] = rec
        approval_instance = kwargs.get('approval_instance') or rec.get_approval_instance()
        approval_instance and approval_instance.after_reject(**kw)

    def reject_from_popup_reject(self, **kwargs):
        return self.do_reject(**kwargs)

    def create_approval_task_line(self, approval_task_line, **kwargs):
        transaction_object = kwargs.get('transaction_object')
        approval_instance = kwargs.get('approval_instance')
        approval_template = kwargs.get('approval_template')
        _logger.info("create %s ", kwargs)

        def ensure_dict(input_data):
            if isinstance(input_data, dict):
                return input_data
            else:
                if have_method(input_data, 'prepare_dict_approval_task_line'):
                    return safe_call_method(input_data, 'prepare_dict_approval_task_line', kwargs=kwargs)
                return safe_call_method(input_data, 'prepare_line_dict', kwargs=kwargs)

        def ensure_list_create(record_list):
            return [ensure_dict(rec) for rec in record_list]

        context = dict(
            self.env.context,
            default_status_approval='waiting_approval',
        )
        if transaction_object:
            context.update(
                default_transaction_id=transaction_object.id,
                default_transaction_model_name=transaction_object._name,
            )
        if kwargs.get("transaction_view_name"):
            context['default_view_name'] = kwargs.get("transaction_view_name")
        if approval_instance:
            context['default_approval_instance_id'] = approval_instance.id
            approval_template = approval_template or approval_instance.approval_template_id
        if approval_template:
            context['default_approval_template_id'] = approval_template.id
            if approval_template.view_name and not context.get('default_view_name'):
                context['default_view_name'] = approval_template.view_name

        return self.with_context(context).create(ensure_list_create(approval_task_line))

    def write(self, vals):
        if 'reject_to_matrix_rule_line' in vals and vals['reject_to_matrix_rule_line']:
            vals['reject_to_method'] = 'to_task_line'
        res = super().write(vals)
        if 'reject_to_matrix_rule_line' in vals:
            self.setup_reject_to_rule_line()
        return res

    @api.model_create_multi
    @api.returns('self', lambda value: value.id)
    def create(self, vals_list):
        for vals in vals_list:
            if 'reject_to_matrix_rule_line' in vals and vals['reject_to_matrix_rule_line']:
                vals['reject_to_method'] = 'to_task_line'

        result = super().create(vals_list)
        result.setup_reject_to_rule_line()
        return result

    def setup_reject_to_rule_line(self):
        for rec in self:
            if rec.reject_to_task_line_id:
                rec.reject_to_method = 'to_task_line'
                reject_to_task_line = self.filtered(lambda r: r.matrix_rule_line == rec.reject_to_matrix_rule_line.id)
                if reject_to_task_line:
                    reject_to_task_line = reject_to_task_line[0].id
                else:
                    reject_to_task_line = self.search([
                        ('transaction_id', '=', rec.transaction_id),
                        ('transaction_model_name', '=', rec.transaction_model_name),
                        ('matrix_rule_line', '=', rec.reject_to_matrix_rule_line.id)], limit=1)
                if reject_to_task_line and reject_to_task_line.id != rec.reject_to_matrix_rule_line.id:
                    rec.reject_to_matrix_rule_line = reject_to_task_line.id


class ApprovalTaskLine(models.Model):
    _name = 'approval.task.line'
    _inherit = ['approval.task.line.assignment.mixin',
                'approval.task.line.access.mixin',
                'approval.task.line.mixin',
                'approval.status.mixin',
                'approval.access.mixin',
                'approval.transaction.able.mixin',
                ]
    _description = 'This is Approval Task Line for Approval helper waiting approval'
    _order = 'id'

    name = fields.Char()
    approval_instance_id = fields.Many2one('approval.instance')
    requester_id = fields.Many2one(
        'res.users', 'Requester',
        default=lambda self: self.env.user,
        help="User who requested the approval."
    )
    reject_to_method = fields.Selection(default='to_requestor')
    reject_to_task_line_id = fields.Many2one('approval.task.line')

    def name_get(self):
        result = []
        for rec in self:
            sign_title = rec.sign_title
            type_name = rec.name or sign_title or rec.id

            if rec.responsible_user_id:
                if sign_title:
                    sign_title = sign_title + ' - '
                else:
                    sign_title = ''
                type_name = f"{sign_title + rec.responsible_user_id.name}"
            elif rec.type_approval == 'user':
                type_name = f"{rec.sign_title or'User'} - {rec.user_id.name}"
            elif rec.type_approval == 'group':
                type_name = f"{rec.sign_title or 'Group'} - {rec.group_id.name}"
            elif rec.type_approval == 'multi_group':
                groups_name = ",".join([r.name for r in rec.group_ids])
                type_name = f"{rec.sign_title or 'Groups'} - [{groups_name}]"
            elif rec.type_approval == 'multi_user':
                groups_name = ",".join([r.name for r in rec.user_ids])
                type_name = f"{rec.sign_title or 'Users'} - [{groups_name}]"
            result.append((rec.id, type_name))

        return result

    def get_users(self):
        """Return daftar user unik sesuai type_approval"""
        self.ensure_one()
        if self.responsible_user_id:
            return self.responsible_user_id
        users = self.env['res.users']

        if self.type_approval == 'user' and hasattr(self, 'user_id') and self.user_id:
            users = self.user_id

        elif self.type_approval == 'group' and hasattr(self, 'group_id') and self.group_id:
            users = self.group_id.users

        elif self.type_approval == 'multi_user' and hasattr(self, 'user_ids') and self.user_ids:
            users = self.user_ids

        elif self.type_approval == 'multi_group' and hasattr(self, 'group_ids') and self.group_ids:
            users = self.group_ids.mapped('users')
        else:
            # === OPSI FALLBACK ===
            if hasattr(self, 'user_id') and self.user_id:
                users |= self.user_id
            if hasattr(self, 'user_ids') and self.user_ids:
                users |= self.user_ids
            if hasattr(self, 'group_id') and self.group_id:
                users |= self.group_id.users
            if hasattr(self, 'group_ids') and self.group_ids:
                users |= self.group_ids.mapped('users')

        return users

    def get_groups(self):
        self.ensure_one()
        groups = self.env['res.groups']

        if self.type_approval == 'group' and hasattr(self, 'group_id') and self.group_id:
            groups = self.group_id
        elif self.type_approval == 'multi_group' and hasattr(self, 'group_ids') and self.group_ids:
            groups = self.group_ids
        else:
            # === OPSI FALLBACK ===
            if hasattr(self, 'group_id') and self.group_id:
                groups |= self.group_id
            if hasattr(self, 'group_ids') and self.group_ids:
                groups |= self.group_ids

        return groups

    def prepare_approval_task_dict(self):
        """Prepare dict untuk create record approval task"""
        self.ensure_one()

        kw = {
            'approval_task_line': self,
            'approval_model': self._name,
            'approval_res_id': self.id
        }
        if self.responsible_user_id:
            kw['user_ids'] = self.responsible_user_id
            return kw

        users = self.env['res.users'].browse()
        groups = self.env['res.groups'].browse()
        if self.type_approval == 'user' and self.user_id:
            users |= self.user_id
        elif self.type_approval == 'group' and self.group_id:
            groups |= self.group_id
        elif self.type_approval == 'multi_user' and self.user_ids:
            users = self.user_ids
        elif self.type_approval == 'multi_group' and self.group_ids:
            groups = self.group_ids
        else:
            # === OPSI FALLBACK ===
            if self.user_id:
                users |= self.user_id
            if self.user_ids:
                users |= self.user_ids
            if self.group_id:
                groups |= self.group_id
            if self.group_ids:
                groups |= self.group_ids
        if users:
            kw['user_ids'] = users
        if groups:
            kw['group_ids'] = groups

        return kw

    def set_approved_status(self, **kwargs):
        self.ensure_one()
        self.write({
            'user_execution_id': self.env.uid,
            'date_execution': fields.Datetime.now(),
            'status_approval': 'approved',
        })

    def set_rejected_status(self, **kwargs):
        self.write({
            'user_execution_id': self.env.uid,
            'date_execution': fields.Datetime.now(),
            'status_approval': 'rejected',
            'reject_reason': kwargs.get('reject_reason') or kwargs.get('reason') or self.env.context.get(
                '__reject_reason')
        })

    def set_waiting_status(self, **kwargs):
        self.write({
            'status_approval': 'waiting_approval'
        })

    def get_all_approval_task_line(self, transaction_id=None, transaction_model_name=None):
        transaction_id = transaction_id or self.transaction_id
        transaction_model_name = transaction_model_name or self.transaction_model_name
        return self.search(
            [('transaction_id', '=', transaction_id), ('transaction_model_name', '=', transaction_model_name)],
            order='id asc')

    def get_next_approval_task_line(self, transaction_id=None, transaction_model_name=None):
        # transaction_id = transaction_id or self.transaction_id
        # transaction_model_name = transaction_model_name or self.transaction_model_name
        # domain =  [('transaction_id', '=', transaction_id), ('transaction_model_name', '=', transaction_model_name),] + self.domain_waiting_status()
        # next_approval_task_line = self.sudo().search(domain, order='id asc', limit=1)
        next_approval_task_line = super(ApprovalTaskLine, self).get_next_approval_task_line(
            transaction_id=transaction_id, transaction_model_name=transaction_model_name
        )
        if next_approval_task_line and next_approval_task_line.status_approval != 'waiting_approval':
            next_approval_task_line.set_waiting_status()
        return next_approval_task_line

    def get_approval_instance(self):
        return self.approval_instance_id

    def get_users_for_notification(self, **kwargs):
        record = self.ensure_one()
        users = kwargs.get('users') or record.get_users()
        company = kwargs.get('company') or self.env.company
        if users:
            return users.get_users_for_notification(company=company)
        else:
            return users

    def send_approval_notification(self, **kwargs):
        self.send_notification(**kwargs)

    def send_rejected_notification(self, **kwargs):
        kwargs = dict(kwargs)
        kwargs['users'] = self.requester_id
        self.send_notification(**kwargs)

    def send_approved_notification(self, **kwargs):
        kwargs = dict(kwargs)
        kwargs['users'] = self.requester_id
        self.send_notification(**kwargs)

    def send_notification(self, **kwargs):
        # implment di module notification
        pass

    def search_responsible_user(self, old_user_id):
        old_user_id = int(old_user_id)
        return self.search([('user_id', '=', old_user_id), ('responsible_user_id', '=', old_user_id)])
