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

from ..tools.utils import safe_call_method

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


class ApprovalTemplateMixin(models.AbstractModel):
    _name = 'approval.template.mixin'
    _rec_name = 'model_id'

    document = fields.Char("Document")
    description = fields.Char("Description")
    model_id = fields.Many2one('ir.model')
    model = fields.Char(related='model_id.model')

    view_id = fields.Many2one(
        'ir.ui.view',
        'Form Transaction',
        domain="[('model', '=', model)]",
    )
    view_name = fields.Char(related='view_id.name')
    action_id = fields.Many2one(
        'ir.actions.act_window',
        'Window Transaction',
        domain="[('res_model', '=', model)]",
    )
    menu_id = fields.Many2one(
        'ir.ui.menu',
        'Menu Transaction',
        ondelete='set null',
    )
    # approval.matrix.mixin
    approval_mode = fields.Selection([
        ('matrix', 'Approval Matrix'),
        ('model', 'By Model'),
    ], required=True, default='matrix')
    approval_matrix_id = fields.Many2one(
        "approval.matrix.rule.mixin", string="Approval Matrix"
    )
    approval_matrix_model = fields.Char()
    approval_matrix_model_id = fields.Many2one('ir.model', string="Target Model", ondelete='set null', )
    # # approval.task.line.mixin
    approval_task_line_model_id = fields.Many2one('ir.model', ondelete='set null', )
    approval_task_line_model = fields.Char(
        related='approval_task_line_model_id.model'
    )
    # approval.status.mixin
    auto_register_approval_task = fields.Boolean()
    approval_task_line_parent_filed = fields.Char(
        help="parent field for approval task line."
    )
    approval_task_line_state_field = fields.Char(
        help='status_approval'
    )
    approval_task_line_state_cancel = fields.Char(
        help="State when cancel"
    )
    approval_task_line_state_reject = fields.Char(
        help="State when reject"
    )
    approval_task_line_state_approved = fields.Char(
        help="State when approved. Leve blank when not need update"
    )
    approval_task_line_state_waiting_approvals = fields.Char(
        help="Waiting Approval for approval_line"
    )
    approval_task_line_users_mode = fields.Selection([
        ('function', 'Function'),
        ('users_field', 'User Field'),
        ('group_field', 'Group Field'),
    ])

    approval_task_line_users_params = fields.Char()

    approval_task_auto_register = fields.Boolean("Auto Register")
    state_field = fields.Char()
    state_reject = fields.Char(help="State when reject")
    state_approved = fields.Char(help="State when approved. Leve blank when not need update")
    state_canceled = fields.Char(help="State when canceled. Leve blank when not need update")
    state_waiting_approvals = fields.Char(help="Waiting Approval for approval_line")

    invoke_validate_request_approval = fields.Char()
    invoke_approval_start = fields.Char()
    invoke_approval_done = fields.Char()

    approve_action_type = fields.Selection([
        ('window_action', 'Window Action'),
        ('server_action', 'Server Action'),
    ])
    approve_window_action_id = fields.Many2one('ir.actions.act_window')
    approve_server_action_id = fields.Many2one('ir.actions.server')
    invoke_before_approve = fields.Char()
    invoke_after_approve = fields.Char()

    reject_action_type = fields.Selection([
        ('window_action', 'Window Action'),
        ('server_action', 'Server Action'),
    ])
    reject_window_action_id = fields.Many2one('ir.actions.act_window')
    reject_server_action_id = fields.Many2one('ir.actions.server')
    invoke_before_reject = fields.Char()
    invoke_after_reject = fields.Char()

    notes_chatter_approved = fields.Boolean("Note Chatter Approve")
    notes_chatter_rejected = fields.Boolean("Note Chatter Rejected")

    reminder_interval_number = fields.Integer(default=1, help="Repeat every x.")
    reminder_interval_type = fields.Selection(
        [('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days'), ('weeks', 'Weeks'), ('months', 'Months')],
        string='Interval Unit', default='weeks'
    )
    notification_reminder_id = fields.Many2one(
        'notification.template',
        ondelete='set null',
        help="Notification template used for reminder notifications."
    )

    notification_approval_id = fields.Many2one(
        'notification.template',
        ondelete='set null',
        help="Notification template used for approval notifications."
    )

    notification_rejection_id = fields.Many2one(
        'notification.template',
        ondelete='set null',
        help="Notification template used for reject notifications."
    )
    notification_approved_id = fields.Many2one(
        'notification.template',
        ondelete='set null',
        help="Notification template used for reject notifications."
    )
    code = fields.Text(
        string='Python Code',
        default=DEFAULT_PYTHON_CODE,
        help="Write Python code that the action will execute. Some variables are "
             "available for use; help about python expression is given in the help tab."
    )
    type_approval_default = fields.Selection([
        ('exception', 'Exception'),
        ('multi_user', 'Users'),
        ('multi_group', 'Groups'),
    ], 'Type Approval', default='exception'
    )
    users_approval_default_ids = fields.Many2many('res.users')
    groups_approval_default_ids = fields.Many2many('res.groups')
    pdf_sign = fields.Selection(
        [('none', 'None'),
         ('approve_is_sign_pdf', 'Sign to Approve'),
         ('approve_form_sign_pdf', 'Sign from Approve'),
         ], default='none', help="""
                none : Not related pdf
                Approve to sign: When approve this instance will propagate to sign pdf.
                Approve from : Sign document will approve this instance when approve will redirect to sign authenticate.
                """
    )
    invoke_get_pdf_document = fields.Char()

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

    def get_state_waiting_approvals(self):
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

    @api.model
    def _get_eval_context(self, approval_instance):
        """ evaluation context to pass to safe_eval """
        transaction_object = approval_instance and approval_instance.get_transaction_object()
        response = {
            'approval_instance': approval_instance,
            'transaction_object': transaction_object,
            'transaction_model_name': self.model,
            'transaction_document': self.document,
            'transaction_description': self.description,
            'approval_template': self,
        }

        result = {
            'env': self.env,
            'uid': self._uid,
            'user': self.env.user,
            'ref': self.env.ref,
            # 'time': tools.safe_eval.time,
            # 'datetime': tools.safe_eval.datetime,
            # 'dateutil': tools.safe_eval.dateutil,
            'timezone': timezone,
            'float_compare': float_compare,
            'b64encode': base64.b64encode,
            'b64decode': base64.b64decode,
            'response': response
        }
        result.update(response)
        return result

    @api.constrains('code')
    def _check_python_code(self):
        for action in self.sudo().filtered('code'):
            msg = test_python_expr(expr=action.code.strip(), mode="exec")
            if msg:
                raise ValidationError(msg)

    def _run_action_code_multi(self, eval_context):
        safe_eval(self.code.strip(), eval_context, mode="exec", nocopy=True)  # nocopy allows to return 'action'
        return eval_context.get('response')

    # Configurasi tambahan
    def get_config_instance(self, approval_instance):
        return self._run_action_code_multi(self._get_eval_context(approval_instance))

    def search_template(self, transaction=None, transaction_model_name=None):
        if transaction:
            transaction_model_name = transaction._name

        if not transaction_model_name:
            raise UserError("Model Name not set")

        return self.search([('model_id.model', '=', transaction_model_name)], limit=1)

    def get_approval_matrix_model(self, default='approval.matrix.rule'):
        return self.approval_matrix_model or default

    def get_approval_matrix(self, **kwargs):
        self.ensure_one()
        if self.approval_mode == 'matrix':
            return self.approval_matrix_id
        approval_matrix_model = self.get_approval_matrix_model()
        if approval_matrix_model and approval_matrix_model in self.env:
            matrix_model = self.env[approval_matrix_model]
            return safe_call_method(
                matrix_model, 'get_approval_matrix_rule', kwargs=kwargs
            )

    def get_approval_line_from_matrix(self, **kwargs):
        self.ensure_one()
        approval_matrix_rule = kwargs.get('approval_matrix_rule') or self.get_approval_matrix(**kwargs)
        if have_method(approval_matrix_rule, 'prepare_list_approval_task_line'):
            return safe_call_method(
                approval_matrix_rule, 'prepare_list_approval_task_line', kwargs=kwargs
            )
        elif have_method(approval_matrix_rule, 'get_approval_task_line'):
            return safe_call_method(
                approval_matrix_rule, 'get_approval_task_line', kwargs=kwargs
            )

    def get_notification_approval(self):
        return self.notification_approval_id

    def get_notification_rejection(self):
        return self.notification_rejection_id

    def get_notification_approved(self):
        return self.notification_approved_id

    def get_next_reminder_datetime(self, from_date_time=None):
        nextcall = from_date_time or fields.Datetime.now()
        nextcall += _intervalTypes[self.reminder_interval_type](self.reminder_interval_number)
        return nextcall

    # handel approval_task_line
    def get_transaction_object(self, **kwargs):
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
        approval_task_line = kwargs.pop('approval_task_line', None)
        if approval_task_line:
            if (
                    approval_task_line
                    and isinstance(approval_task_line, models.BaseModel)
                    and have_method(approval_task_line, 'get_transaction_object')
            ):
                return safe_call_method(approval_task_line, 'get_transaction_object', kwargs=kwargs)

            approval_template = kwargs.get('approval_template')
            if not isinstance(approval_template, models.BaseModel):
                approval_template = self
            if approval_template.approval_task_line_parent_filed:
                return getattr(approval_task_line, approval_template.approval_task_line_parent_filed, None)
            else:
                return self.env[approval_template.model]
        return None

    def get_domain_waiting_status(self, **kwargs):
        if not self:
            return []
        approval_template = self.ensure_one()
        domain = []
        waiting_status = approval_template.get_state_waiting_approvals()
        if waiting_status and approval_template.state_field:
            domain = [(approval_template.state_field, 'in', waiting_status)]
        return domain

    @api.model
    def get_approval_task_line_transaction_id(self, approval_task_line, **kwargs):
        transaction_object = self.get_transaction_object(approval_task_line=approval_task_line, **kwargs)
        if transaction_object:
            return transaction_object.id
        return None

    def get_approval_task_line_state_waiting_approvals(self, **kwargs):
        if self.approval_task_line_state_waiting_approvals:
            return self.approval_task_line_state_waiting_approvals.split(',')
        else:
            return ['waiting_approval']

    def get_approval_task_line_domain_waiting_status(self, approval_task_line, **kwargs):
        if not self:
            return None
        self.ensure_one()
        transaction_id = self.get_approval_task_line_transaction_id(approval_task_line, **kwargs)
        if self.approval_task_line_parent_filed:
            domain = [(self.approval_task_line_parent_filed, '=', transaction_id)]
        else:
            domain = [('transaction_id', '=', transaction_id), ('transaction_model_name', '=', self.model_id.model)]

        waiting_status = self.get_approval_task_line_state_waiting_approvals(
            approval_task_line=approval_task_line, **kwargs
        )
        if waiting_status and self.approval_task_line_state_field:
            domain_waiting_status = [(self.approval_task_line_state_field, 'in', waiting_status)]
        domain.extend(domain_waiting_status or [])
        return domain

    def get_approval_template_from_approval_task_line(self, approval_task_line, **kwargs):
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
            return self.search(
                [('get_approval_template_from_approval_task_line.model', '=', approval_task_line._name)],
                limit=1
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
        # transaction_object = approval_template.get_approval_task_line_transaction_object(
        #     approval_task_line, **kwargs
        # )

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

    def search_template_by_model(self, transaction_model_name):
        if not transaction_model_name:
            self.browse()
        return self.search([('model_id.model', '=', transaction_model_name)], limit=1)

    def search_template_by_approval_task_line_model(self, model_name):
        if not model_name:
            self.browse()
        return self.search([('approval_task_line_model_id.model', '=', model_name)], limit=1)

    def get_approval_groups_or_users(self, **kwargs):
        approval_dict = {}
        approval_task_line = kwargs.get('approval_task_line')
        if approval_task_line:
            if self.approval_task_line_users_mode == 'function':
                approval_dict['user_ids'] = safe_call_method(
                    approval_task_line, self.approval_task_line_users_params, kwargs=kwargs
                )
            elif self.approval_task_line_users_mode == 'users_field':
                approval_dict['user_ids'] = getattr(
                    approval_task_line, self.approval_task_line_users_params, None
                )
            elif self.approval_task_line_users_mode == 'group_field':
                approval_dict['group_ids'] = getattr(
                    approval_task_line, self.approval_task_line_users_params, None
                )
        else:
            _logger.info("get_approval_groups_or_users")

        return approval_dict

    def get_users(self, **kwargs):
        user_ids = self.env['res.users']
        approval_task_line = kwargs.get('approval_task_line')
        if approval_task_line:
            if self.approval_task_line_users_mode == 'function':
                user_ids = safe_call_method(
                    approval_task_line, self.approval_task_line_users_params, kwargs=kwargs
                ) or user_ids
            elif self.approval_task_line_users_mode == 'users_field':
                user_ids = getattr(
                    approval_task_line, self.approval_task_line_users_params, user_ids
                )
            elif self.approval_task_line_users_mode == 'group_field':
                group_ids = getattr(
                    approval_task_line, self.approval_task_line_users_params, None
                )
                if group_ids:
                    user_ids = group_ids.users
        else:
            _logger.info("get_users")

        return user_ids

    def get_access_approval(self, **kwargs):
        approval_task_line = kwargs.get('approval_task_line')
        company = getattr(approval_task_line, 'company_id', None)
        users = self.get_users(**kwargs).get_users_for_approval(company=company)
        return bool(self.env.user in users)


class ApprovalTemplate(models.Model):
    _name = 'approval.template'
    _inherit = ['approval.template.mixin']
    _description = """
    Template configuration from instance template easy register/unregister approval.task
    """

    _sql_constraints = [
        ('model_id_unique', 'unique(model_id)', 'Model must be uniq!')
    ]

    approval_matrix_id = fields.Many2one("approval.matrix.rule", string="Matrix")

    def migrate_approval_task(self, raise_exception=True, skip_send_notification=True, reset_reminder=False):
        env = self.env
        for template in self:
            model, field_status, waiting_status = template.model, template.get_state_field(), template.get_state_waiting_approvals()
            transaction_ids = [0]
            records = env['approval.task'].search([('transaction_model_name', '=', template.model)])
            for rec in records:
                try:
                    approval_instance = env['approval.instance'].create_or_get(
                        transaction_model_name=rec.transaction_model_name,
                        transaction_id=rec.transaction_id
                    )
                    if approval_instance.is_status_waiting_approval():
                        approval_instance.register_approval_task_line(
                            skip_send_notification=skip_send_notification)
                        transaction_ids.append(rec.transaction_id)
                    else:
                        approval_instance.unregister_approval_task_line()
                except:
                    _logger.exception("register_approval_task_line 1")
                    if raise_exception:
                        raise

            records = env[model].search([(field_status, 'in', waiting_status), ('id', 'not in', transaction_ids)])
            for rec in records:
                _logger.info("info %s ", rec)
                try:
                    approval_instance = env['approval.instance'].create_or_get(
                        transaction_model_name=model,
                        transaction_id=rec.id
                    )
                    approval_instance.register_approval_task_line()
                    transaction_ids.append(rec.id)
                except:
                    _logger.exception("register_approval_task_line 2")
                    if raise_exception:
                        raise
