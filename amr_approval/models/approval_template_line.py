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
    ],default='specific')
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
    ],help="""
Mode user mengambil Approval task Assign
Assign task bisa bedasarkan group, user atau employee atau kombinasi.
Data ini akan di kirim ke approval.task agar bisa menentukan user mana yang bisa melakukan approal
- Fields : System akan mencari bedasarkan field. untuk multiple fields dengan comma dilimter
- Fuction : System akan memangil fungsi itu untuk mendapatak groups atau user    
    """)
    approval_mode_function = fields.Char()
    approval_mode_fields = fields.Char(default='user_id')

    field_user_execution = fields.Char()
    field_date_execution = fields.Char()
    field_user_delegation = fields.Char()
    field_started_task_time = fields.Char()
    field_reason = fields.Char()

    method_start_task = fields.Char()
    method_set_waiting_approval_state = fields.Char()
    method_set_approved_state = fields.Char()
    method_set_rejected_state = fields.Char()
    method_set_canceled_state = fields.Char()
    method_set_to_draft_state = fields.Char()

    def invoke_method(self, approval_task_line, method_name, kwargs=None, raise_exceptions=False):
        atts_method_name = f"method_{method_name} or {method_name}"
        object_method_name = getattr(self, atts_method_name)
        if have_method(approval_task_line, object_method_name):
            return safe_call_method(approval_task_line, object_method_name, kwargs=kwargs)
        elif have_method(approval_task_line, method_name):
            return safe_call_method(approval_task_line, method_name, kwargs=kwargs)
        elif have_method(self, method_name):
            return safe_call_method(self, method_name, args=[approval_task_line, kwargs])
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
            domain = [('transaction_id', '=', transaction_id),
                      ('transaction_model_name', '=', self.parent_model or transaction_model_name)]

        if isinstance(status, (list, set, tuple)):
            domain.append((self.get_state_field(), 'in', self.get_state_waiting_approvals()))
        elif status is not None:
            domain.append((self.get_state_field(), '=', status))
        return domain

    @api.model
    def domain_waiting_status(self, transaction_id, transaction_model_name=None):
        return self.domain_status(transaction_id, self.get_state_waiting_approvals(),
                                  transaction_model_name=transaction_model_name)

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

    def get_all_approval_task_line(self, status=None, **kwargs):
        approval_template_line = self.get_approval_template_line(**kwargs)
        if not approval_template_line:
            raise ValueError("approval_template_line Not found")
        approval_task_line = approval_template_line.env[approval_template_line.model]
        transaction_object = approval_template_line.get_transaction_object(**kwargs)
        if transaction_object and isinstance(transaction_object, models.BaseModel):
            domain = approval_template_line.domain_status(
                transaction_object.id, status, transaction_model_name=transaction_object._name
            )

            return approval_task_line.search(domain)
        else:
            return approval_task_line

    def get_one_approval_task_line(self, status=None, **kwargs):
        approval_template_line = self.get_approval_template_line(**kwargs)
        if not approval_template_line:
            raise ValueError("approval_template_line Not found")
        approval_task_line = approval_template_line.env[approval_template_line.model]
        transaction_object = approval_template_line.get_transaction_object(**kwargs)
        if transaction_object and isinstance(transaction_object, models.BaseModel):
            domain = approval_template_line.domain_status(
                transaction_object.id, status, transaction_model_name=transaction_object._name
            )
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
            user_ids = approval_task_line.mapped(self.field_user_execution)
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
            write = {
                self.state_field: kwargs.get('state_waiting_approval') or self.get_state_waiting_approvals()[0]
            }
            field_started_task_time = self.field_started_task_time
            started_task_time = None
            if self.field_started_task_time:
                started_task_time = kwargs.get(self.field_started_task_time) or kwargs.get('started_task_time')
            elif kwargs.get('started_task_time'):
                started_task_time = kwargs.get('started_task_time')
            if started_task_time and field_started_task_time:
                write[field_started_task_time] = started_task_time
            if self.field_date_execution:
                write[self.field_date_execution] = False
            if self.field_reason:
                write[self.field_reason] = False
            if self.field_user_delegation:
                write[self.field_user_delegation] = False
            approval_task_line.write(write)
        else:
            raise UserError("Invalid configuration approval")

    def set_approved_status(self, approval_task_line=None, **kwargs):
        if approval_task_line and self.state_field and self.state_approved:
            write = {
                self.state_field: self.state_approved
            }
            if self.field_date_execution:
                write[self.field_date_execution] = fields.Datetime.now()
            if self.field_user_execution:
                write[self.field_user_execution] = self.env.user.id
            if self.field_user_delegation and kwargs.get('user_delegation'):
                write[self.field_user_delegation] = kwargs.get('user_delegation')
            if self.field_reason and kwargs.get('reason'):
                write[self.field_reason] = kwargs.get('reason')

            approval_task_line.write(write)
            return kwargs
        else:
            raise UserError("Invalid configuration approval")

    def set_rejected_status(self, approval_task_line=None, **kwargs):
        if approval_task_line and self.state_field and self.state_rejected:
            write = {
                self.state_field: self.state_rejected
            }
            if self.field_date_execution:
                write[self.field_date_execution] = fields.Datetime.now()
            if self.field_user_execution:
                write[self.field_user_execution] = self.env.user.id
            if self.field_user_delegation and kwargs.get('user_delegation'):
                write[self.field_user_delegation] = kwargs.get('user_delegation')
            if self.field_reason and kwargs.get('reason'):
                write[self.field_reason] = kwargs.get('reason')

            approval_task_line.write(write)
            return kwargs
        else:
            raise UserError("Invalid configuration approval")

    def set_canceled_status(self, approval_task_line=None, **kwargs):
        if approval_task_line and self.state_field and self.state_canceled:
            write = {
                self.state_field: self.state_canceled
            }
            if self.field_date_execution:
                write[self.field_date_execution] = fields.Datetime.now()
            if self.field_user_execution:
                write[self.field_user_execution] = self.env.user.id
            if self.field_user_delegation and kwargs.get('user_delegation'):
                write[self.field_user_delegation] = kwargs.get('user_delegation')
            if self.field_reason and kwargs.get('reason'):
                write[self.field_reason] = kwargs.get('reason')

            approval_task_line.write(write)

            return kwargs
        else:
            raise UserError("Invalid configuration approval")

    # def get_user_delegation(self):
    #     return

    def check_action_right(self, approval_task_line, kw):
        def check_doa():
            users = self.get_users(approval_task_line=approval_task_line, **kw)
            user_delegations = self.env['user.delegation'].get_all_delegations(
                delegatee_id=self.env.user.id, delegator_id=users.ids, limit=1
            )
            if user_delegations:
                kw['user_delegations'] = user_delegations
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
        return kw

    def start_waiting_approval(self, approval_task_line=None, **kwargs):
        if not approval_task_line:
            return
        approval_task = kwargs.get('approval_task')
        if approval_task.request_approval_task_date:
            kwargs['started_task_time'] = approval_task.request_approval_task_date
            if approval_task_line:
                approval_task_line = approval_task_line.with_context(
                    __skip_auto_register_approval_task_line_status=True
                )
        self.set_waiting_approval_status(approval_task_line=approval_task_line, **kwargs)

    def do_approve(self, approval_task_line, kw):
        kw['approval_template_line'] = self.ensure_one()
        kw.pop('approval_task_line', None)
        return self.env['approval.task.line'].do_approve_approval_task_line(approval_task_line, **kw)

    def do_reject(self, approval_task_line, kw):
        kw['approval_template_line'] = self.ensure_one()
        kw.pop('approval_task_line', None)
        return self.env['approval.task.line'].do_reject_approval_task_line(approval_task_line, **kw)

    def clear_approval(self, **kwargs):
        if not self:
            _logger.warning("No Template for celar Approval")
            return self
        rec = self.ensure_one()
        transaction_object = self.get_transaction_object(**kwargs)
        if not transaction_object:
            return self
        data = self.get_all_approval_task_line(transaction_object=transaction_object)
        if data:
            data.unlink()
        return self


class ApprovalTemplateLine(models.Model):
    _name = 'approval.template.line'
    _inherit = ['approval.template.line.mixin']
    _description = """
    Template configuration from instance template easy register/unregister approval.task
    """

    _sql_constraints = [
        ('model_id_unique', 'unique(model_id)', 'Model must be uniq!')
    ]
