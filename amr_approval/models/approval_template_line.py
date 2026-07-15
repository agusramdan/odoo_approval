# -*- coding: utf-8 -*-

import base64
import logging

from pytz import timezone
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare
from odoo.tools.safe_eval import safe_eval, test_python_expr
from pytz import timezone
from ..tools.utils import have_method, safe_call_method

_logger = logging.getLogger(__name__)

_intervalTypes = {
    'days': lambda interval: relativedelta(days=interval),
    'hours': lambda interval: relativedelta(hours=interval),
    'weeks': lambda interval: relativedelta(days=7 * interval),
    'months': lambda interval: relativedelta(months=interval),
    'minutes': lambda interval: relativedelta(minutes=interval),
}

DEFAULT_PYTHON_CODE = """
# Available variables:
#  - env: Odoo Environment on which the action is triggered
#  - time, datetime, dateutil, timezone: useful Python libraries
#  - float_compare: Odoo function to compare floats based on specific precisions
#  - log: log(message, level='info'): logging function to record debug information in ir.logging table
#  - UserError: Warning Exception to use with raise
#  - Command: x2Many commands namespace
#  - approval_instance
#  - approval_template
# To return an response, assign: response = {...}

\n\n\n\n
"""

EXCLUDE_MODELS = {
    # Technical
    'ir.model',
    'ir.model.fields',
    'ir.cron',
    'ir.ui.view',
    'ir.actions.act_window',

    # Security
    'res.users',
    'res.groups',
    'res.company',
    'res.config.settings',

    # Messaging
    'mail.message',
    'mail.followers',
    'mail.activity',

    #
    'internal.data.event',
    'internal.data.event.config',
    'external.data.event',
}

EXCLUDE_PREFIXES = (
    'ir.',
    'bus.',
    'base.',
    'mail.',
    'web.',
    'internal.data.',
    'external.data.',
    'application.',
    'approval.',
    'notification.'
    'user.delegation.'
    'whatsapp.'
)


def is_excluded(model_name):
    return model_name in EXCLUDE_MODELS or model_name.startswith(EXCLUDE_PREFIXES)


class ApprovalTaskLineBaseMixin(models.AbstractModel):
    _inherit = 'base'

    def get_approval_template_line(self):
        return self.env['approval.template.line'].search_template_line_by_model(self._name)

    def _is_excluded(self):
        return is_excluded(self._name)

    def state_leave_waiting_approvals(self, approval_template_line, state_approval, create_date=None):
        rec = self
        al = None
        if approval_template_line.state_approved == state_approval:
            _logger.info("To Approve %s , %s .", self, state_approval)
            al = approval_template_line.create_approval_audit_log_approved(
                approval_task_line=rec,
                action_type='approve',
                name='Approval',
                create_date=create_date or fields.Datetime.now(),
            )
        elif approval_template_line.state_reject == state_approval:
            _logger.info("To Reject %s , %s .", self, state_approval)
            al = approval_template_line.create_approval_audit_log_rejected(
                approval_task_line=rec,
                action_type='reject',
                name='Reject',
                create_date=create_date or fields.Datetime.now(),
            )
        elif approval_template_line.state_canceled == state_approval:
            al = approval_template_line.create_approval_audit_log_canceled(
                approval_task_line=rec,
                action_type='cancel',
                name='Cancel',
                create_date=create_date or fields.Datetime.now(),
            )
            _logger.info("To Cancel %s , %s .", self, state_approval)
        else:
            _logger.warning("%s , %s .", self, state_approval)
        return al

    def write(self, vals):
        if self.is_transient() or self._is_excluded() or self.env.context.get(
                '__skip_approval_task_line_status') or self.is_transient():
            return super().write(vals)
        approval_template_line = self.get_approval_template_line()
        if not approval_template_line:
            return super().write(vals)
        approval_template = approval_template_line.approval_template_id
        if not approval_template:
            approval_template = self.env['approval.template'].get_approval_template_from_approval_task_line(self)
        old = None
        state_field = None
        trx_change = {}

        if approval_template_line and approval_template_line.state_field:
            state_field = approval_template_line.state_field
            if state_field in vals:
                old = {r.id: getattr(r, state_field, None) for r in self}
        res = super().write(vals)
        if old:
            state_waiting_approvals = approval_template_line.get_state_waiting_approvals()
            for rec in self:
                state_approval = getattr(rec, state_field)
                if old[rec.id] in state_waiting_approvals and state_approval not in state_waiting_approvals:
                    transaction_object = approval_template_line.get_transaction_object(
                        approval_template=approval_template,
                        approval_template_line=approval_template_line,
                        approval_task_line=rec,
                    )
                    trx_change[transaction_object.id] = transaction_object
                    rec.state_leave_waiting_approvals(approval_template_line, state_approval)

        if (
                trx_change and
                approval_template_line and
                approval_template_line.auto_register_approval_task and
                not self.env.context.get('__skip_auto_register_approval_task_line_status')
        ):
            for trx_id, transaction_object in trx_change.items():
                approval_task_line = None
                approval_instance = None
                if transaction_object:
                    approval_instance = self.env['approval.instance'].create_or_get(
                        transaction=transaction_object,
                        approval_template=approval_template,
                        approval_template_line=approval_template_line,
                        raise_exception_without_template=False,
                    )
                    if approval_instance:
                        approval_task_line = approval_instance.get_next_approval_task_line()
                if (
                        approval_task_line and
                        transaction_object and
                        approval_instance and
                        approval_instance.is_status_waiting_approval()
                ):
                    if have_method(transaction_object, 'register_to_approval_task'):
                        transaction_object.register_to_approval_task(
                            approval_task_line=approval_task_line,
                            approval_template=approval_template,
                            approval_template_line=approval_template_line,
                        )
                    else:
                        approval_instance.register_approval_task_line(
                            transaction_object=transaction_object,
                            approval_task_line=approval_task_line,
                            approval_template=approval_template,
                            approval_template_line=approval_template_line,
                        )

        return res


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
    ])
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
        help="State when cancel"
    )
    state_reject = fields.Char(
        help="State when reject"
    )
    state_approved = fields.Char(
        help="State when approved. Leve blank when not need update"
    )
    state_waiting_approvals = fields.Char(
        help="Waiting Approval for approval_line"
    )
    users_mode = fields.Selection([
        ('function', 'Function'),
        ('field', 'Field'),
    ])

    users_params = fields.Char()

    invoke_validate_request_approval = fields.Char()
    invoke_approval_start = fields.Char()
    invoke_approval_done = fields.Char()

    approve_action_type = fields.Selection([
        ('window_action', 'Window Action'),
        ('server_action', 'Server Action'),
        ('method', 'Method'),
    ])
    approve_window_action_id = fields.Many2one('ir.actions.act_window')
    approve_server_action_id = fields.Many2one('ir.actions.server')
    invoke_method_approve = fields.Char()

    reject_action_type = fields.Selection([
        ('window_action', 'Window Action'),
        ('server_action', 'Server Action'),
        ('method', 'Method'),
    ])
    reject_window_action_id = fields.Many2one('ir.actions.act_window')
    reject_server_action_id = fields.Many2one('ir.actions.server')
    invoke_method_reject = fields.Char()

    cancel_action_type = fields.Selection([
        ('window_action', 'Window Action'),
        ('server_action', 'Server Action'),
        ('method', 'Method'),
    ])
    cancel_window_action_id = fields.Many2one('ir.actions.act_window')
    cancel_server_action_id = fields.Many2one('ir.actions.server')
    invoke_method_cancel = fields.Char()

    def invoke_method(self, transaction_object, method_name, kwargs=None, raise_exceptions=False):
        atts_method_name = f"invoke_{method_name}"
        object_method_name = getattr(self, atts_method_name)
        if have_method(transaction_object, object_method_name):
            return safe_call_method(transaction_object, object_method_name, kwargs=kwargs)
        else:
            if raise_exceptions:
                raise UserError("object_method_name %s not found." % object_method_name)
            _logger.info("%s object_method_name %s not found.", transaction_object, object_method_name)
            return None

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

    def get_state_reject(self):
        return self.state_reject

    def get_state_approved(self):
        return self.state_approved

    def prepare_dict(self):
        return {'model_id': self.model_id.id}

    def get_transaction_status(self, transaction):
        rec = self.ensure_one()
        state_field = rec.get_state_field()
        return transaction and getattr(transaction, state_field)

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

    @api.model
    def get_approval_task_line_transaction_id(self, approval_task_line, **kwargs):
        transaction_object = self.get_transaction_object(approval_task_line=approval_task_line, **kwargs)
        if transaction_object:
            return transaction_object.id
        return None

    def get_domain_waiting_status(self, approval_task_line, **kwargs):
        if not self:
            return None
        self.ensure_one()
        domain_waiting_status = None
        transaction_id = self.get_transaction_id(approval_task_line, **kwargs)
        if self.parent_filed:
            domain = [(self.parent_filed, '=', transaction_id)]
        else:
            domain = [('transaction_id', '=', transaction_id), ('transaction_model_name', '=', self.model_id.model)]

        waiting_status = self.get_state_waiting_approvals(
            approval_task_line=approval_task_line, **kwargs
        )
        if waiting_status and self.state_field:
            domain_waiting_status = [(self.state_field, 'in', waiting_status)]
        domain.extend(domain_waiting_status or [])
        return domain

    def get_approval_template(self, approval_task_line, **kwargs):
        approval_template = None
        if approval_task_line:
            if have_method(approval_task_line, 'get_approval_template'):
                approval_template = safe_call_method(approval_task_line, 'get_approval_template', kwargs=kwargs)
            if not approval_template and have_method(approval_task_line, 'get_transaction_object'):
                transaction_object = safe_call_method(approval_task_line, 'get_transaction_object', kwargs=kwargs)
                approval_template = self.search_template(transaction_object)
        else:
            if self:
                approval_template = self[0]
            else:
                approval_template = self.browse()

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
        return approval_template or self.browse()

    def lookup_approval_template(self, **kwargs):
        approval_template = kwargs.get('approval_template')
        if approval_template and isinstance(approval_template, models.BaseModel):
            return approval_template

        approval_task_line = kwargs.pop('approval_task_line')
        approval_template = self.get_approval_template_from_approval_task_line(
            approval_task_line, **kwargs
        )
        if not approval_template:
            transaction_object = kwargs.pop('transaction_object')
            if transaction_object:
                return self.search_template(
                    transaction=transaction_object,
                    transaction_model_name=kwargs.get('transaction_model_name')
                )

        if not approval_template:
            return self.browse()

        return approval_template

    def get_next_approval_task_line(self, approval_task_line=None, **kwargs):
        approval_template = kwargs.get('approval_template') or self
        if not approval_template and len(approval_template) > 1:
            approval_template = approval_template[0]
        if not isinstance(approval_task_line, models.BaseModel) and approval_template:
            approval_task_line = self.env[approval_template.approval_task_line_model]
        if not approval_template and not self:
            approval_template = self.get_approval_template_from_approval_task_line(approval_task_line)
        domain = approval_template.get_approval_task_line_domain_waiting_status(approval_task_line, **kwargs)
        return approval_task_line.search(domain, limit=1)

    def search_template_line_by_model(self, model_name):
        if not model_name:
            self.browse()
        return self.search([('model_id.model', '=', model_name)], limit=1)

    def search_template_by_approval_task_line_model(self, model_name):
        if not model_name:
            self.browse()
        return self.search([('approval_task_line_model_id.model', '=', model_name)], limit=1)

    def get_users(self, **kwargs):
        user_ids = self.env['res.users'].browse()
        approval_task_line = kwargs.get('approval_task_line')
        users_params = self.users_params
        if approval_task_line and users_params and self.users_mode:
            candidate_users = None
            if self.users_mode == 'function':
                candidate_users = safe_call_method(
                    approval_task_line, users_params, kwargs=kwargs
                )
            elif self.users_mode == 'field':
                candidate_users = getattr(
                    approval_task_line, self.users_params, None
                )
            if candidate_users and isinstance(candidate_users, models.BaseModel):
                if candidate_users._name == 'res.users':
                    user_ids = candidate_users
                elif candidate_users._name == 'res.groups':
                    user_ids = candidate_users.users
                elif candidate_users._name == 'hr.employee':
                    user_ids = candidate_users.user_id
        else:
            _logger.info("get_approval_line_users")

        return user_ids

    def get_access_approval(self, **kwargs):
        approval_task_line = kwargs.get('approval_task_line')
        company = getattr(approval_task_line, 'company_id', None)
        users = self.get_users(**kwargs).get_users_for_approval(company=company)
        return bool(self.env.user in users)

    def set_waiting_status(self, approval_task_line, kwargs):
        if approval_task_line and self.state_field and self.state_waiting_approvals:
            wa = self.get_state_waiting_approvals()
            approval_task_line.write({
                self.state_field: wa[0]
            })
        else:
            raise UserError("Invalid configuration approval")

    def set_approved_status(self, approval_task_line, kwargs):
        if approval_task_line and self.state_field and self.state_approved:
            approval_task_line.write({
                self.state_field: self.state_approved
            })
        else:
            raise UserError("Invalid configuration approval")

    def set_rejected_status(self, approval_task_line, kwargs):
        if approval_task_line and self.state_field and self.state_reject:
            approval_task_line.write({
                self.state_field: self.state_reject
            })
        else:
            raise UserError("Invalid configuration approval")

    def set_canceled_status(self, approval_task_line, kwargs):
        if approval_task_line and self.state_field and self.state_canceled:
            approval_task_line.write({
                self.state_field: self.state_canceled
            })
        else:
            raise UserError("Invalid configuration approval")

    def do_approve(self, approval_task_line, kwargs):
        rec = self.ensure_one()
        kw = dict(kwargs)
        approval_task_line = approval_task_line.with_context(
            __skip_create_approval_audit_log=True,
            __skip_approval_task_line_status=True,
            __skip_auto_register_approval_task_line_status=True,
        )
        kw['approval_template_line'] = approval_template = rec
        kw['approval_task_line'] = approval_task_line
        kw['transaction_object'] = transaction_object = self.get_transaction_object(**kw)
        kw['approval_instance'] = approval_instance = self.get_approval_instance(**kw)

        if not approval_instance.access_approval:
            raise UserError("User not allow to approve")

        approval_instance.before_approve(**kw)
        if approval_task_line:
            if approval_template.approve_action_type == 'method':
                method = approval_template.invoke_method_approve
            else:
                method = 'set_approved_status'
            if not have_method(approval_task_line, method):
                result = safe_call_method(approval_task_line, method, kwargs=kw)
            else:
                rec.set_approved_status(approval_task_line)
                result = approval_task_line
        else:
            result = None
        rec.create_approval_audit_log_approved(**kw)
        approval_task_line_next = rec.get_next_approval_task_line(**kw)
        kw['approval_task_line_next'] = approval_task_line_next
        kw['is_approval_done'] = not approval_task_line_next
        approval_instance.after_approve(**kw)
        return result

    def do_cancel(self, approval_task_line, kwargs):
        rec = self.ensure_one()
        kw = dict(kwargs)
        approval_task_line = approval_task_line.with_context(
            __skip_create_approval_audit_log=True,
            __skip_approval_task_line_status=True,
            __skip_auto_register_approval_task_line_status=True,
        )
        kw['approval_template_line'] = approval_template = rec
        kw['approval_task_line'] = approval_task_line
        kw['transaction_object'] = transaction_object = self.get_transaction_object(**kw)
        kw['approval_instance'] = approval_instance = self.get_approval_instance(**kw)

        if not approval_instance.access_approval:
            raise UserError("User not allow to approve")

        approval_instance.before_approve(**kw)
        if approval_task_line:
            if approval_template.canceled_action_type == 'method':
                method = approval_template.invoke_method_approve
            else:
                method = 'set_canceled_status'
            if not have_method(approval_task_line, method):
                result = safe_call_method(approval_task_line, method, kwargs=kw)
            else:
                rec.set_canceled_status(approval_task_line)
                result = approval_task_line
        else:
            result = None
        rec.create_approval_audit_log_approved(**kw)
        approval_task_line_next = rec.get_next_approval_task_line(**kw)
        kw['approval_task_line_next'] = approval_task_line_next
        kw['is_approval_done'] = not approval_task_line_next
        approval_instance.after_approve(**kw)
        return result

    def do_reject(self, approval_task_line, kwargs):
        rec = self.ensure_one()
        kw = dict(kwargs)
        approval_task_line = approval_task_line.with_context(
            __skip_create_approval_audit_log=True,
            __skip_approval_task_line_status=True,
            __skip_auto_register_approval_task_line_status=True,
        )
        kw['approval_template'] = approval_template = rec
        kw['approval_task_line'] = approval_task_line
        kw['transaction_object'] = transaction_object = self.get_transaction_object(**kw)
        kw['approval_instance'] = approval_instance = self.get_approval_instance(**kw)

        if not approval_instance.access_approval:
            raise UserError("User not allow to reject")

        approval_instance.before_reject(**kw)
        is_approval_done = False
        approval_task_line_next = None
        approval_task_line_between = None

        reject_to_method = getattr(approval_task_line, 'reject_to_method', 'to_requestor')
        if reject_to_method == 'to_requestor':
            is_approval_done = True
            approval_task_line_between = safe_call_method(approval_task_line, 'get_approval_start_task')
        else:
            if reject_to_method == 'to_task_line':
                approval_task_line_next = safe_call_method(approval_task_line, 'get_reject_to_task_line')
                approval_task_line_between = safe_call_method(
                    approval_task_line, 'get_approval_start_task',
                    kwargs={'start_task': approval_task_line_next})
                # self.get_approval_start_task(approval_task_line_next)
            elif reject_to_method == 'to_previous':
                # approval_task_line_next = self.get_previous_approval_task_line()
                approval_task_line_next = safe_call_method(approval_task_line, 'get_previous_approval_task_line')
            elif reject_to_method == 'legacy':
                legacy = safe_call_method(approval_task_line, 'reject_method_legacy', kwargs=kw)
                if legacy:
                    approval_task_line_next = legacy[0]
                    approval_task_line_between = legacy[1]
                # approval_task_line_next, approval_task_line_between = self.reject_method_legacy(reason, **kwargs)
            else:
                approval_task_line_next = kwargs.get('approval_task_line_next')
                approval_task_line_between = kwargs.get(
                    'approve_task_line_between'
                ) or safe_call_method(
                    approval_task_line, 'get_approval_start_task',
                    kwargs={'start_task': approval_task_line_next})
            is_approval_done = not approval_task_line_next
        if is_approval_done:
            kw['is_approval_done'] = True
            kw['is_rejected'] = True
        else:
            kw['approval_task_line_next'] = approval_task_line_next
        kw['approve_task_task_between'] = approval_task_line_between
        kw['approve_task_line'] = kw['approve_task_line_reject'] = approval_task_line

        if approval_task_line:
            if approval_template.reject_action_type == 'method':
                method = approval_template.invoke_method_approve
            else:
                method = 'set_rejected_status'
            if not have_method(approval_task_line, method):
                result = safe_call_method(approval_task_line, method, kwargs=kw)
            else:
                rec.set_rejected_status(approval_task_line)
                result = approval_task_line
        else:
            result = None

        self.create_approval_audit_log_rejected(**kw)
        approval_instance.after_reject(**kw)
        if not is_approval_done and approval_task_line_next:
            # todo bila set waiting status tidak ada
            safe_call_method(approval_task_line_next, 'set_waiting_status', kwargs=kw)
            # approval_task_line_next.set_waiting_status(**kw)
            if approval_task_line_between:
                # todo bila set waiting status tidak ada
                safe_call_method(approval_task_line_next, 'set_waiting_status', kwargs=kw)
                # approval_task_line_between.set_waiting_status(**kw)
        return result

    def _create_approval_audit_log(self, **kwargs):
        if self.env.context.get('__skip_create_approval_audit_log'):
            return None

        self.ensure_one()
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
        return self._create_approval_audit_log(**kw)

    def create_approval_audit_log_rejected(self, **kwargs):
        kw = dict(kwargs)
        kw['action_type'] = 'reject'
        return self._create_approval_audit_log(**kw)

    def create_approval_audit_log_canceled(self, **kwargs):
        kw = dict(kwargs)
        kw['action_type'] = 'cancel'
        return self._create_approval_audit_log(**kw)


class ApprovalTemplateLine(models.Model):
    _name = 'approval.template.line'
    _inherit = ['approval.template.line.mixin']
    _description = """
    Template configuration from instance template easy register/unregister approval.task
    """

    _sql_constraints = [
        ('model_id_unique', 'unique(model_id)', 'Model must be uniq!')
    ]
