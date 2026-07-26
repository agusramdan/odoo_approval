# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError
from ..tools.utils import have_method, safe_call_method

_logger = logging.getLogger(__name__)


class ApprovalTemplateLineMixin(models.AbstractModel):
    _name = 'approval.template.line.mixin'
    _rec_name = 'model_id'

    model_id = fields.Many2one('ir.model')
    model = fields.Char(related='model_id.model')
    # approval.status.mixin
    auto_register_approval_task = fields.Boolean()

    parent_mode = fields.Selection([
        ('agnostic', 'Agnostic'),
        ('specific', 'Specific'),
    ], default='specific')
    # when parent mode specific parent model mandatory
    approval_template_id = fields.Many2one('approval.template', ondelete='set null', )
    parent_model_id = fields.Many2one('ir.model', related='approval_template_id.model_id')
    parent_model = fields.Char(
        related='parent_model_id.model'
    )

    parent_filed = fields.Char(
        help="parent field for approval task line."
    )
    state_field = fields.Char(
        help='status_approval'
    )
    state_canceled = fields.Char(
        help="State when cancel by Requester"
    )
    state_rejected = fields.Char(
        help="State when reject"
    )
    state_approved = fields.Char(
        help="State when approved. Leve blank when not need update"
    )
    state_waiting_approvals = fields.Char(
        help="Waiting Approval for approval_line"
    )
    state_reset = fields.Char(
        help="Reset by Requester"
    )
    approval_mode = fields.Selection([
        ('function', 'Function'),
        ('fields', 'Fields'),
    ], help="""
Mode user mengambil Approval task Assign
Assign task bisa bedasarkan group, user atau employee atau kombinasi.
Data ini akan di kirim ke approval.task agar bisa menentukan user mana yang bisa melakukan approal
- Fields : System akan mencari bedasarkan field. untuk multiple fields dengan comma dilimter
- Fuction : System akan memangil fungsi itu untuk mendapatak groups atau user    
    """)
    approval_mode_function = fields.Char()
    approval_mode_fields = fields.Char(default='user_id')

    field_sign_title = fields.Char()
    field_user_execution_id = fields.Char()
    field_date_execution = fields.Char()
    field_user_delegation_id = fields.Char()
    field_started_task_time = fields.Char()
    field_reason = fields.Char()
    # responsible mapping
    field_responsible_rule_id = fields.Char()
    field_responsible_id = fields.Char()
    field_responsible_user_id = fields.Char()

    # reject
    field_reject_to_method = fields.Char()
    field_matrix_rule_line_model = fields.Char()
    field_matrix_rule_line_id = fields.Char()
    field_reject_to_matrix_rule_line_id = fields.Char()
    field_reject_to_task_id = fields.Char()
    #
    field_type_approval = fields.Char()
    field_user_id = fields.Char("User ID")
    field_group_id = fields.Char("Group ID")
    field_user_ids = fields.Char("Users IDS")
    field_group_ids = fields.Char("Groups IDS")

    method_start_task = fields.Char()
    method_set_waiting_approval_state = fields.Char()
    method_set_approved_state = fields.Char()
    method_set_rejected_state = fields.Char()
    method_set_canceled_state = fields.Char()
    method_set_to_draft_state = fields.Char()

    reject_to_method_default = fields.Selection([
        ('to_requestor', "To Requestor"),
        ('to_previous', "To Previous"),
        ('to_task_line', "To Task Line"),
    ], default='to_requestor', readonly=True)

    @api.model_create_multi
    @api.returns('self', lambda value: value.id)
    def create(self, vals_list):
        for vals in vals_list:
            if 'field_user_execution' in vals:
                vals['field_user_execution_id'] = vals.pop('field_user_execution')
            if 'field_user_delegation' in vals:
                vals['field_user_delegation_id'] = vals.pop('field_user_delegation')

        return super().create(vals_list)

    def write(self, vals):
        if 'field_user_execution' in vals:
            vals['field_user_execution_id'] = vals.pop('field_user_execution')
        if 'field_user_delegation' in vals:
            vals['field_user_delegation_id'] = vals.pop('field_user_delegation')
        return super().write(vals)

    def get_field_mapping(self):
        mapping = {
            field_name[6:]: getattr(self, field_name)
            for field_name in self._fields
            if field_name.startswith('field_') and getattr(self, field_name, False)
        }
        return mapping

    def safe_data_approval_task_line(self, approval_task_line):
        """
        Normalize approval task line values so that they only contain
        fields existing in the target model.

        :param list[dict] approval_task_line:
            Source values.
        :return list[dict]:
            Safe values ready for create().
        """
        self.ensure_one()

        model_target = self.env[self.model]
        target_fields = model_target._fields
        mapping = self.get_field_mapping() or {}
        _logger.info("mapping %s", mapping)
        result = []

        for vals in approval_task_line:
            if isinstance(vals, models.BaseModel) or not isinstance(vals, dict):
                result.append(vals)
                continue

            safe_vals = {}

            for field_name, value in vals.items():
                # Field exists on target model
                if field_name in target_fields:
                    safe_vals[field_name] = value
                    _logger.info("accept field %s", field_name)
                    continue

                # Try mapping
                mapped_field = mapping.get(field_name)
                if mapped_field and mapped_field in target_fields:
                    _logger.info("convert to %s -> %s", field_name, mapped_field)
                    safe_vals[mapped_field] = value
                else:
                    _logger.info("remove field %s", field_name)

            result.append(safe_vals)

        return result

    def invoke_method(self, approval_task_line, method_name, kwargs=None, raise_exceptions=False):
        atts_method_name = f"method_{method_name}"
        object_method_name = getattr(self, atts_method_name)
        if object_method_name and have_method(approval_task_line, object_method_name):
            return safe_call_method(approval_task_line, object_method_name, kwargs=kwargs)
        elif have_method(approval_task_line, method_name):
            return safe_call_method(approval_task_line, method_name, kwargs=kwargs)
        elif have_method(self, method_name):
            kw = {
                'approval_task_line': approval_task_line
            }
            kw.update(kwargs or {})
            return safe_call_method(self, method_name, kwargs=kw)
        else:
            message = "object_method_name %s not found or %s ." % (object_method_name, method_name)
            if raise_exceptions:
                raise UserError(message)
            _logger.info(message)
            return None

    @api.model
    def domain_status(self, transaction_id, status, transaction_model_name=None):
        if self.approval_template_id:
            domain = [(self.parent_filed, '=', transaction_id)]
        else:
            domain = [
                ('transaction_id', '=', transaction_id),
                ('transaction_model_name', '=', transaction_model_name or self.parent_model)
            ]

        if isinstance(status, (list, set, tuple)):
            domain.append((self.get_state_field(), 'in', status))
        elif status is not None:
            domain.append((self.get_state_field(), '=', status))
        return domain

    @api.model
    def domain_waiting_status(self, transaction_id, transaction_model_name=None):
        return self.domain_status(
            transaction_id,
            self.get_state_waiting_approvals(),
            transaction_model_name=transaction_model_name,
        )

    def get_state_waiting_approvals(self, **kwargs):
        if self.state_waiting_approvals:
            return self.state_waiting_approvals.split(',')
        else:
            return ['waiting_approval']

    def get_state_field(self):
        state_field = 'state'
        if not self:
            return state_field
        return self.state_field or state_field

    def get_state_rejected(self):
        return self.state_rejected or 'draft'

    def get_state_approved(self):
        return self.state_approved or 'approve'

    def get_state_canceled(self):
        return self.state_canceled

    def get_state_reset(self):
        return self.state_reset

    def is_status_waiting_approval(self, transaction):
        if not self or not transaction:
            return False
        rec = self.ensure_one()
        state_field = rec.get_state_field()
        state_waiting_approvals = rec.get_state_waiting_approvals()
        return transaction and getattr(transaction, state_field) in state_waiting_approvals

    # handel approval_task_line
    @api.model
    def get_approval_instance(self, **kwargs):
        approval_instance = kwargs.get('approval_instance')
        if (
                approval_instance
                and isinstance(approval_instance, models.BaseModel)
        ):
            return approval_instance
        return None

    def get_transaction_object(self, **kwargs):
        approval_task_line = kwargs.pop('approval_task_line', None)

        if approval_task_line:
            if self.parent_filed:
                return getattr(approval_task_line, self.parent_filed, None)
            if (
                    approval_task_line
                    and isinstance(approval_task_line, models.BaseModel)
                    and have_method(approval_task_line, 'get_transaction_object')
            ):
                return safe_call_method(approval_task_line, 'get_transaction_object', kwargs=kwargs)

            approval_template = kwargs.get('approval_template')
            if not isinstance(approval_template, models.BaseModel):
                approval_template = self
            if approval_template:
                return approval_template.get_transaction_object(
                    **kwargs
                )
            # else:
            #     return self.env[self.model]

        transaction_object = kwargs.get('transaction_object')
        if (
                transaction_object
                and isinstance(transaction_object, models.BaseModel)
        ):
            return transaction_object

        approval_instance = kwargs.get('approval_instance')
        if (
                approval_instance
                and isinstance(approval_instance, models.BaseModel)
        ):
            return safe_call_method(approval_instance, 'get_transaction_object', kwargs=kwargs)

        return None

    def get_domain_waiting_status(self, approval_task_line, **kwargs):
        if not self:
            return None
        self.ensure_one()
        transaction_object = self.get_transaction_object(approval_task_line=approval_task_line, **kwargs)
        if not transaction_object:
            return None
        return self.domain_waiting_status(transaction_object.id)

    def get_approval_template_line(self, **kwargs):
        if self:
            return self
        approval_template_line = kwargs.get('approval_template_line')
        if approval_template_line:
            return approval_template_line
        approval_template = self.get_approval_template(**kwargs)
        return approval_template.approval_template_line_id

    def get_approval_template(self, approval_task_line=None, **kwargs):
        if self and self[0].approval_template_id:
            return self[0].approval_template_id

        approval_template = kwargs.get('approval_template')
        if approval_template:
            return approval_template

        if approval_task_line:
            if have_method(approval_task_line, 'get_approval_template'):
                approval_template = safe_call_method(approval_task_line, 'get_approval_template', kwargs=kwargs)
            if not approval_template and have_method(approval_task_line, 'get_transaction_object'):
                transaction_object = safe_call_method(approval_task_line, 'get_transaction_object', kwargs=kwargs)
                approval_template = self.approval_template_id.search_template(transaction_object)

        if not approval_template and isinstance(approval_task_line, models.BaseModel):
            approval_template_line = self.search(
                [('model_id.model', '=', approval_task_line._name)],
                limit=1,
            )
            if approval_template_line and approval_template_line.approval_template_id:
                return approval_template_line.approval_template_id
            approval_template = self.approval_template_id.search(
                [('approval_task_line_model_id.model_id.model', '=', approval_task_line._name)],
                limit=1,
            )
        return approval_template or self.approval_template_id.browse()

    def get_all_approved_task_line(self, **kwargs):
        kwargs.pop('status', None)
        return self.get_all_approval_task_line(status=self.get_state_approved(), **kwargs)

    def get_all_approval_task_line(self, status=None, **kwargs):
        approval_task_line = self.env[self.model].browse()
        transaction_object = self.get_transaction_object(**kwargs)
        if transaction_object and isinstance(transaction_object, models.BaseModel):
            domain = self.domain_status(
                transaction_object.id, status, transaction_model_name=transaction_object._name
            )
            return approval_task_line.search(domain)
        else:
            return approval_task_line

    def get_one_approval_task_line(self, status=None, **kwargs):
        approval_task_line = self.env[self.model].browse()
        transaction_object = self.get_transaction_object(**kwargs)
        if transaction_object and isinstance(transaction_object, models.BaseModel):
            domain = self.domain_status(
                transaction_object.id, status, transaction_model_name=transaction_object._name
            )
            _logger.info("domain %s", domain)
            return approval_task_line.search(domain, limit=1)
        else:
            return approval_task_line

    def get_next_approval_task_line(self, **kwargs):
        return self.get_one_approval_task_line(status=self.get_state_waiting_approvals(), **kwargs)

    def get_last_approval_task_line(self, **kwargs):
        kwargs.pop('status', None)
        approval_task_line = self.get_all_approval_task_line(status=None, **kwargs)
        if len(approval_task_line) > 1:
            return approval_task_line[-1]
        return approval_task_line

    def search_template_line_by_model(self, model_name):
        if not model_name:
            self.browse()
        return self.search([('model_id.model', '=', model_name)], limit=1)

    def get_approver_data(self, **kwargs):
        """
        {
           'user_ids' : records res.users,
           'groups_ids' : records res.group,
        }
        """
        approval_task_line = kwargs.get('approval_task_line')

        def to_dict(records, result_dict):
            result_dict = result_dict or {}
            if records and isinstance(records, models.Model):
                if records._name == 'res.users':
                    records_old = result_dict.get('user_ids') or self.env['res.users'].browse()
                    records_old |= records
                    result_dict['user_ids'] = records_old
                elif records._name == 'res.groups':
                    records_old = result_dict.get('group_ids') or self.env['res.groups'].browse()
                    records_old |= records
                    result_dict['group_ids'] = records_old
                elif records._name == 'hr.employee':
                    records_old = result_dict.get('user_ids') or self.env['res.users'].browse()
                    records_old |= records.user_id
                    result_dict['user_ids'] = records_old
            return result_dict

        result = {}
        if approval_task_line and self.approval_mode:
            if self.approval_mode == 'function':
                candidate_access = safe_call_method(
                    approval_task_line, self.approval_mode_function, kwargs=kwargs
                )
                if candidate_access:
                    if isinstance(candidate_access, dict):
                        return candidate_access
                    return to_dict(candidate_access, result)
            elif self.approval_mode == 'fields':
                if self.approval_mode_fields:
                    fields_list = self.approval_mode_fields.split(',')
                    for field_name in fields_list:
                        result = to_dict(getattr(approval_task_line, field_name, None), result)
        else:
            _logger.info("get_approval_line_users")
        return result

    def get_user_execution(self, approval_task_line=None, **kwargs):
        user_ids = self.env['res.users'].browse()
        if approval_task_line:
            user_ids = approval_task_line.mapped(self.field_user_execution_id)
        return user_ids

    def get_users(self, **kwargs):
        result_dict = self.get_approver_data(**kwargs)
        user_ids = result_dict.get('user_ids') or self.env['res.users'].browse()
        group_ids = result_dict.get('group_ids')
        if group_ids:
            user_ids |= group_ids.user_id
        return user_ids

    def get_access_approval(self, **kwargs):
        approval_task_line = kwargs.get('approval_task_line')
        company = getattr(approval_task_line, 'company_id', None)
        users = self.get_users(**kwargs).get_users_for_approval(company=company)
        return bool(self.env.user in users)

    def set_waiting_approval_status(self, approval_task_line=None, **kwargs):
        if approval_task_line and self.state_field and self.state_waiting_approvals:
            write = self.safe_data_approval_task_line([{
                'started_task_time': False,
                'user_execution_id': False,
                'date_execution': False,
                'user_delegation_id': False,
                'reason': False
            }])[0]
            write[self.state_field] = self.get_state_waiting_approvals()[0]
            # write.pop('transaction_id', None)
            # write.pop('transaction_model_name', None)
            # if self.parent_filed:
            #     write.pop(self.parent_filed, None)

            approval_task_line.write(write)
        else:
            raise UserError("Invalid configuration set_waiting_approval_status field %s , value %s " % (
                self.state_field, self.state_waiting_approvals))

    def set_approved_state(self, approval_task_line=None, **kwargs):
        return self.set_approved_status(approval_task_line=approval_task_line, **kwargs)

    def set_approved_status(self, approval_task_line=None, **kwargs):
        if approval_task_line and self.state_field and self.state_approved:
            kwargs.setdefault('date_execution', fields.Datetime.now())
            kwargs.setdefault('user_execution_id', self.env.user.id)
            write = self.safe_data_approval_task_line([kwargs])[0]
            write.pop('transaction_id', None)
            write.pop('transaction_model_name', None)
            if self.parent_filed:
                write.pop(self.parent_filed, None)
            write[self.state_field] = self.state_approved
            _logger.info("set_approved_status %s , %s", approval_task_line, write)
            approval_task_line.write(write)
            return kwargs
        else:
            raise UserError("Invalid configuration approval set_approved_status field %s , value %s " % (
                self.state_field, self.state_approved))

    def set_rejected_state(self, approval_task_line=None, **kwargs):
        return self.set_rejected_status(approval_task_line=approval_task_line, **kwargs)

    def set_rejected_status(self, approval_task_line=None, **kwargs):
        if approval_task_line and self.state_field and self.state_rejected:
            kwargs.setdefault('date_execution', fields.Datetime.now())
            kwargs.setdefault('user_execution_id', self.env.user.id)
            write = self.safe_data_approval_task_line([kwargs])[0]
            write.pop('transaction_id', None)
            write.pop('transaction_model_name', None)
            if self.parent_filed:
                write.pop(self.parent_filed, None)
            write[self.state_field] = self.state_rejected
            _logger.info("set_rejected_status %s , %s", approval_task_line, write)
            approval_task_line.write(write)
            return kwargs
        else:
            raise UserError("Invalid configuration approval field set_rejected_status %s , value %s " % (
                self.state_field, self.state_rejected))

    def set_canceled_status(self, approval_task_line=None, **kwargs):
        if approval_task_line and self.state_field and self.state_canceled:
            kwargs.setdefault('date_execution', fields.Datetime.now())
            kwargs.setdefault('user_execution_id', self.env.user.id)
            write = self.safe_data_approval_task_line([kwargs])[0]
            write.pop('transaction_id', None)
            write.pop('transaction_model_name', None)
            if self.parent_filed:
                write.pop(self.parent_filed, None)
            write[self.state_field] = self.state_canceled
            approval_task_line.write(write)

            return kwargs
        else:
            raise UserError(
                "Invalid configuration approval  field %s , value %s " % (self.state_field, self.state_canceled))

    # def get_user_delegation(self):
    #     return

    def check_action_right(self, approval_task_line, kw):
        result = {
            'date_execution': fields.Datetime.now(),
            'user_execution_id': self.env.user.id,
            'user_execution': self.env.user,
            'user_approver_id': self.env.user.id,
            'user_approver': self.env.user
        }

        def check_doa():
            users = self.get_users(approval_task_line=approval_task_line, **kw)
            user_delegation = self.env['user.delegation'].get_all_delegations(
                delegatee_id=self.env.user.id, delegator_id=users.ids, limit=1
            )
            if user_delegation:
                result['execution_method'] = user_delegation.get_execution_method()
                result['user_delegation'] = user_delegation
                result['user_delegation_id'] = user_delegation.id
                result['user_approver_id'] = user_delegation.delegator_id.id
                result['user_approver'] = user_delegation.delegator_id
            else:
                raise UserError("User not allow to approval.")

        if hasattr(approval_task_line, 'access_approval'):
            if not approval_task_line.access_approval:
                check_doa()
        else:
            if 'approval_instance' in kw:
                approval_instance = kw['approval_instance']
                if not approval_instance.access_approval:
                    check_doa()
        return result

    def start_waiting_approval(self, approval_task_line=None, **kwargs):
        if not approval_task_line or not self:
            return
        approval_task = kwargs.get('approval_task')
        state_waiting_approvals = self.get_state_waiting_approvals()
        if approval_task_line and self.state_field and state_waiting_approvals:
            kw = dict(kwargs)
            kw.pop('transaction_id', None)
            kw.pop('transaction_model_name', None)
            if self.parent_filed:
                kw.pop('transaction_model_name', None)
            kw.update({
                'date_execution': False,
                'user_execution_id': False,
                'user_delegation_id': False,
                'reason': False
            })
            if approval_task.request_approval_task_date:
                kw['started_task_time'] = approval_task.request_approval_task_date
                if approval_task_line:
                    approval_task_line = approval_task_line.with_context(
                        __skip_auto_register_approval_task_line_status=True
                    )
            write = self.safe_data_approval_task_line([kw])[0]
            write[self.state_field] = state_waiting_approvals[0]
            approval_task_line.write(write)
        else:
            raise UserError("Invalid configuration set_waiting_approval_status field %s , value %s " % (
                self.state_field, self.state_waiting_approvals))

    def do_approve(self, approval_task_line_approve, kw):
        _logger.info("approval_task_line do_approve %s kw", kw)
        approval_template_line = self.ensure_one()
        kw.pop('approval_task_line', None)
        if not approval_task_line_approve or not isinstance(approval_task_line_approve, models.Model):
            raise ValueError("Invalid approval_task_line. ")
        env = approval_task_line_approve.env
        if env.context.get('__has_call_do_approve_approval_task_line'):
            # skip recall
            return None
        skip_create_approval_audit_log = env.context.get('__skip_create_approval_audit_log')
        approval_task_line_approve = approval_task_line_approve.with_context(
            __skip_create_approval_audit_log=True,
            __has_call_do_approve_approval_task_line=True,
        )
        approval_template_line.check_action_right(approval_task_line_approve, kw)
        kw['approval_template_line'] = approval_template_line
        kw['approval_task_line'] = approval_task_line_approve
        kw.pop('approval_task_line_next', None)
        kw.pop('approval_task_line_approve', None)
        approval_template = approval_template_line.get_approval_template(**kw)
        approval_template.before_approve(**kw)
        _logger.info("approval_task_line set_approved_state %s kw", kw)
        approval_template_line.invoke_method(
            approval_task_line_approve, 'set_approved_state', kwargs=kw, raise_exceptions=True
        )
        approval_task_line_next = approval_template_line.get_next_approval_task_line(
            **kw
        )
        if approval_task_line_next == approval_task_line_approve:
            raise UserError("Approval task cannot change status.")

        if not skip_create_approval_audit_log:
            kw['approval_audit_log'] = env['approval.audit.log'].create_approval_audit_log_approved(**kw)

        is_approval_done = not approval_task_line_next
        if is_approval_done:
            kw['is_approval_done'] = True
            kw['is_approve'] = True
        else:
            kw['approval_task_line_next'] = approval_task_line_next

        approval_template.after_approve(**kw)
        if is_approval_done:
            approval_template.done_approval(**kw)

    def do_reject(self, approval_task_line_reject, kw):
        kw['approval_template_line'] = approval_template_line = self.ensure_one()
        kw.pop('approval_task_line', None)
        if not approval_task_line_reject or not isinstance(approval_task_line_reject, models.Model):
            raise ValueError("Invalid approval_task_line. ")
        env = approval_task_line_reject.env

        if env.context.get('__has_call_do_reject_approval_task_line'):
            # skip recall
            return None
        skip_create_approval_audit_log = env.context.get('__has_call_do_reject_approval_task_line')
        approval_task_line_reject = approval_task_line_reject.with_context(
            __has_call_do_reject_approval_task_line=True,
            __skip_create_approval_audit_log=True,
            __skip_approval_task_line_status=True,
            __skip_auto_register_approval_task_line_status=True,
        )
        approval_template_line.check_action_right(approval_task_line_reject, kw)
        kw['approval_task_line'] = approval_task_line_reject
        kw['approval_template_line'] = approval_template_line
        kw['approval_task_line_reject'] = approval_task_line_reject
        approval_template = approval_template_line.get_approval_template(**kw)
        # before reject
        approval_template.before_reject(**kw)
        reject_plan = self.plan_to_reject(**kw)
        _logger.info("reject plan %s .", reject_plan)
        approval_template_line.set_rejected_status(**kw)
        approval_task_line_next = reject_plan.get('approval_task_line_next')
        approval_task_line_between = reject_plan.get('approval_task_line_between')
        is_approval_done = not approval_task_line_next
        if is_approval_done:
            kw['is_approval_done'] = True
            kw['is_rejected'] = True
        else:
            kw['approval_task_line_next'] = approval_task_line_next
        kw['approval_task_line_between'] = approval_task_line_between
        kw['approval_task_line'] = kw['approval_task_line_reject'] = approval_task_line_reject
        if not skip_create_approval_audit_log:
            kw['approval_audit_log'] = env['approval.audit.log'].create_approval_audit_log_rejected(**kw)
        # after_reject
        approval_template.after_reject(**kw)
        if is_approval_done:
            approval_template.done_approval(**kw)
        elif approval_task_line_between:
            kwargs = dict(kw)
            kwargs['approval_task_line'] = approval_task_line_between
            approval_template_line.set_waiting_approval_status(**kwargs)

        return kw

    @api.model
    def get_approval_task_line_between(self, start_task, end_task, approve_task_lines):
        """
        Get list approval from start_task to this object
        """
        approve_task_line_between = approve_task_lines.browse()
        found_start = not start_task
        for task in approve_task_lines:
            if found_start:
                if end_task.id == task.id:
                    break
                approve_task_line_between |= task
            elif task.id == start_task.id:
                found_start = True

        return approve_task_line_between

    @api.model
    def plan_to_reject(self, approval_task_line_reject=None, **kwargs):
        """
        return
        {
        'approval_task_line_reject' : reject
        'approval_task_line_next' : next approval task
        'approval_task_line_between' : empty or multiple record between approval_task_line and approval_task_line_next
        }
        """

        if not isinstance(approval_task_line_reject, models.Model):
            return {}
        template_line = self.ensure_one()
        approval_task_line_between = approval_task_line_reject.browse()
        approval_task_line_next = approval_task_line_reject.browse()
        result = {
            'approval_task_line_reject': approval_task_line_reject,
            'approval_task_line_between': approval_task_line_between,
            'approval_task_line_next': approval_task_line_next
        }
        # env = approval_task_line_reject.env
        # template_line = env['approval.template.line']
        # template_line = template_line.search_template_line_by_model(approval_task_line_reject._name)
        # if not template_line:
        #     return result
        field_reject_to_method = template_line.field_reject_to_method or 'reject_to_method'
        field_reject_to_task_id = template_line.field_reject_to_task_id or 'reject_to_task_id'
        reject_to_method = getattr(
            approval_task_line_reject, field_reject_to_method, template_line.reject_to_method_default
        )
        _logger.info("reject_to_method %s ", reject_to_method)
        if not reject_to_method or reject_to_method == 'to_requestor':
            approval_task_lines = self.get_all_approved_task_line(**kwargs)
            approval_task_line_between = template_line.get_approval_task_line_between(
                None, approval_task_line_reject, approval_task_lines
            )
            _logger.info("reject_to_method %s ", approval_task_line_between)
        elif reject_to_method == 'to_task_line':
            approval_task_line_next = getattr(approval_task_line_reject, field_reject_to_task_id, None)
            if not approval_task_line_next:
                raise ValueError("Invalid data reject to task. form %s" % approval_task_line_reject)
            approval_task_lines = self.get_all_approved_task_line(**kwargs)
            approval_task_line_between = template_line.get_approval_task_line_between(
                approval_task_line_next, approval_task_line_reject, approval_task_lines
            )
        elif reject_to_method == 'to_previous':
            approval_task_line_next = template_line.get_previous_approval_task_line(
                approval_task_line_reject, **kwargs
            )
        elif reject_to_method == 'legacy':
            approval_task_line_next, approval_task_line_between = approval_task_line_reject.reject_method_legacy(
                **kwargs)
        else:
            approval_task_line_next = kwargs.get('approval_task_line_next')
            approval_task_line_between = kwargs.get(
                'approval_task_task_between'
            ) or template_line.get_approval_task_line_between(
                approval_task_line_next, approval_task_line_reject, **kwargs
            )
        result['approval_task_line_next'] = approval_task_line_next
        result['approval_task_line_between'] = approval_task_line_between
        result['approval_task_line_reject'] = approval_task_line_reject
        return result

    @api.model
    def is_matrix_rule_line_to_requestor(self, matrix_rule_line):
        return False

    def setup_reject_to_rule_line(self, approval_task_lines=None, **kwargs):
        # approval_task_line = approval_task_lines or self.get_all_approval_task_line()
        if not approval_task_lines:
            _logger.info("No approval_task_line")
            return

        matrix_task_line_mapping = {}
        for rec in approval_task_lines:
            matrix_rule_line_id = getattr(rec, self.field_matrix_rule_line_id or 'matrix_rule_line_id', None)
            if matrix_rule_line_id:
                matrix_rule_line_id = int(matrix_rule_line_id)
                matrix_task_line_mapping.setdefault(matrix_rule_line_id, rec.id)

            reject_to_matrix_rule_line_id = getattr(
                rec, self.field_reject_to_matrix_rule_line_id or 'reject_to_matrix_rule_line_id', None
            )

            if reject_to_matrix_rule_line_id:
                # reject_to_matrix_rule_line_id = int(reject_to_matrix_rule_line_id)
                reject_to_task_line = matrix_task_line_mapping.get(int(reject_to_matrix_rule_line_id))
                data = None
                if reject_to_task_line:
                    # rec.reject_to_method = 'to_task_line'
                    data = self.safe_data_approval_task_line([{
                        'reject_to_method': 'to_task_line',
                        'reject_to_task_id': reject_to_task_line,
                    }])[0]
                elif self.is_matrix_rule_line_to_requestor(reject_to_matrix_rule_line_id):
                    data = self.safe_data_approval_task_line([{
                        'reject_to_method': 'to_requestor',
                        'reject_to_task_id': False,
                    }])[0]
                else:
                    _logger.warning("Not found task line form %s, rec %s", reject_to_matrix_rule_line_id, rec)

                if not data:
                    _logger.info("No Config reject_to_method")
                    continue
                else:
                    _logger.info("write data %s , %s", rec, data)
                rec.write(data)

    def clear_approval(self, **kwargs):
        if not self:
            _logger.warning("No Template for celar Approval")
            return self
        # rec = self.ensure_one()
        transaction_object = self.get_transaction_object(**kwargs)
        if not transaction_object:
            return self
        data = self.get_all_approval_task_line(transaction_object=transaction_object)
        if data:
            data.unlink()
        return self

    def create_approval_task_line(self, approval_task_line, **kwargs):
        _logger.info("Call create_approval_task_line")
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
            if self.parent_filed:
                context[f"default_{self.parent_filed}"] = transaction_object.id
        # if kwargs.get("transaction_view_name"):
        #     context['default_view_name'] = kwargs.get("transaction_view_name")
        if approval_instance:
            context['default_approval_instance_id'] = approval_instance.id
            approval_template = approval_template or approval_instance.approval_template_id
        if approval_template:
            context['default_approval_template_id'] = approval_template.id
            # if approval_template.view_name and not context.get('default_view_name'):
            #     context['default_view_name'] = approval_template.view_name
        _logger.info("approval_task_line %s ", approval_task_line)
        approval_task_line = self.safe_data_approval_task_line(approval_task_line)
        _logger.info("safe_data_approval_task_line %s ", approval_task_line)
        approval_task_line = ensure_list_create(approval_task_line)
        _logger.info("approval_task_line %s ", approval_task_line)
        return self.env[self.model].sudo().with_context(context).create(approval_task_line)


class ApprovalTemplateLine(models.Model):
    _name = 'approval.template.line'
    _inherit = ['approval.template.line.mixin']
    _description = """
    Template configuration from instance template easy register/unregister approval.task
    """

    _sql_constraints = [
        ('model_id_unique', 'unique(model_id)', 'Model must be uniq!')
    ]
