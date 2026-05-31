# -*- coding: utf-8 -*-

import base64
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare
from odoo.tools.safe_eval import safe_eval, test_python_expr
from pytz import timezone

from ..tools.utils import safe_call_method

from ..tools.utils import have_method, safe_call_method

_logger = logging.getLogger(__name__)


class ApprovalTemplateMixin(models.AbstractModel):
    _name = 'approval.template.mixin'
    _rec_name = 'model_id'

    document = fields.Char("Document")
    description = fields.Char("Description")

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
    approval_matrix_model_id = fields.Many2one('ir.model', string="Target Model")
    # # approval.task.line.mixin
    approval_task_line_model_id = fields.Many2one('ir.model')
    approval_task_line_model = fields.Char(
        related='approval_task_line_model_id.model'
    )

    state_field = fields.Char()
    state_reject = fields.Char(help="State when reject")
    state_approved = fields.Char(help="State when approved. Leve blank when not need update")
    state_waiting_approvals = fields.Char(help="Waiting Approval for approval_line")

    invoke_validate_request_approval = fields.Char()
    invoke_approval_start = fields.Char()
    invoke_approval_done = fields.Char()
    invoke_before_approve = fields.Char()
    invoke_after_approve = fields.Char()
    invoke_before_reject = fields.Char()
    invoke_after_reject = fields.Char()

    notes_chatter_approved = fields.Boolean("Note Chatter Approve")
    notes_chatter_rejected = fields.Boolean("Note Chatter Rejected")

    notification_approval_id = fields.Many2one(
        'notification.template',
        help="Notification template used for approval notifications."
    )
    notification_rejection_id = fields.Many2one(
        'notification.template',
        help="Notification template used for reject notifications."
    )
    notification_approved_id = fields.Many2one(
        'notification.template',
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

    def invoke_method(self, transaction_object, method_name, kwargs=None):
        atts_method_name = f"invoke_{method_name}"
        object_method_name = getattr(self, atts_method_name)
        safe_call_method(transaction_object, object_method_name, kwargs=kwargs)

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
            return safe_call_method(approval_matrix_rule, 'get_approval_task_line', kwargs=kwargs)


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

    def migrate_approval_task(self, raise_exception=True, skip_send_notification=True):
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
                        approval_instance.register_approval_transaction_task(
                            skip_send_notification=skip_send_notification)
                        transaction_ids.append(rec.transaction_id)
                    else:
                        approval_instance.unregister_approval_transaction_task()
                except:
                    _logger.exception("register_approval_transaction_task 1")
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
                    approval_instance.register_approval_transaction_task()
                    transaction_ids.append(rec.id)
                except:
                    _logger.exception("register_approval_transaction_task 2")
                    if raise_exception:
                        raise
