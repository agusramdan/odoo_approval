# -*- coding: utf-8 -*-

import base64
import logging

from lxml import etree
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
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
DEFAULT_CODE = """
# Available variables:
#  - transaction_object 
#----------------------
result = transaction_object.id>0
"""

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
#  - transaction_object 
# To return an response, assign: response = {...}

\n\n\n\n
"""
# access_request_approval_action
# access_approve_action
# access_reject_action
# access_cancel_approval_action
# access_reset_to_draft_action

APPROVAL_BUTTONS = [
    {
        "action": "request_approval",
        "label": "Request Approval",
        "access_field": "access_request_approval_action",
        "class": "oe_highlight",
    },
    {
        "action": "approve",
        "label": "Approve",
        "access_field": "access_approve_action",
        "class": "oe_highlight",
    },
    {
        "action": "reject",
        "label": "Reject",
        "access_field": "access_reject_action",
        "class": "oe_highlight",
    },
    {
        "action": "cancel",
        "label": "Cancel",
        "access_field": "access_cancel_action",
        "class": "oe_highlight",
    },
    {
        "action": "reset_to_draft",
        "label": "Reset To Draft",
        "access_field": "access_reset_to_draft_action",
        "class": None,
    },
]


class ApprovalTemplateMixin(models.AbstractModel):
    _name = 'approval.template.mixin'
    _rec_name = 'model_id'

    document = fields.Char("Document")
    description = fields.Char("Description")
    model_id = fields.Many2one('ir.model')
    model = fields.Char(related='model_id.model')
    generate_field_approval_task_line = fields.Boolean()
    generate_field_approval_task_line_id = fields.Many2one(
        'ir.model.fields',
        'Generate x_approval_task_line_',
        readonly=True, ondelete='set null',
    )

    generate_view_id = fields.Many2one(
        'ir.ui.view',
        'Generate Form',
        readonly=True, ondelete='set null',
    )
    view_id = fields.Many2one(
        'ir.ui.view',
        'Form Transaction',
        domain="[('model', '=', model)]",
    )
    view_name = fields.Char()
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
    approval_task_line_editable = fields.Boolean(
        help='Akan menampilkan button untuk menampilkan form yang bisa edit approval task list. '
             'Sehinggar requester bisa secara custom menentukan siapa saja yang akan menjadi approval nya.'
    )
    approval_mode = fields.Selection([
        ('matrix', 'Approval Matrix'),
        ('model', 'By Model'),
    ])
    approval_matrix_id = fields.Many2one(
        "approval.matrix.rule.mixin", string="Approval Matrix", ondelete='set null',
    )
    approval_matrix_model = fields.Char()
    approval_matrix_model_id = fields.Many2one('ir.model', string="Target Model", ondelete='set null', )
    # # approval.task.line.mixin
    approval_task_line_model_id = fields.Many2one('ir.model', ondelete='set null', )
    approval_task_line_model = fields.Char(
        related='approval_task_line_model_id.model'
    )
    approval_task_line_page = fields.Boolean("Approval Page")
    approval_task_line_field = fields.Char('Line Field')

    approval_template_line_id = fields.Many2one(
        'approval.template.line', compute='compute_approval_template_line_id',
    )
    # approval.status.mixin
    auto_register_approval_task = fields.Boolean()
    #
    # approval_task_line_parent_filed = fields.Char(
    #     help="parent field for approval task line."
    # )
    # approval_task_line_state_field = fields.Char(
    #     help='status_approval'
    # )
    # approval_task_line_state_cancel = fields.Char(
    #     help="State when cancel"
    # )
    # approval_task_line_state_reject = fields.Char(
    #     help="State when reject"
    # )
    # approval_task_line_state_approved = fields.Char(
    #     help="State when approved. Leve blank when not need update"
    # )
    # approval_task_line_state_waiting_approvals = fields.Char(
    #     help="Waiting Approval for approval_line"
    # )
    # approval_task_line_users_mode = fields.Selection([
    #     ('function', 'Function'),
    #     ('users_field', 'User Field'),
    #     ('group_field', 'Group Field'),
    # ])
    #
    # approval_task_line_users_params = fields.Char()
    # deprecated end
    # approval_task_auto_register = fields.Boolean("Auto Register")

    need_approval_mode = fields.Selection([
        ('field', 'Field'),
        ('function', 'Function'),
        ('code', 'Code'),
    ])
    need_approval_field = fields.Char(
        help="Filed document boolean for need approval."
    )
    need_approval_function = fields.Char(
        help="Code document boolean for need approval."
    )
    need_approval_code = fields.Text(
        default=DEFAULT_CODE,
        help="Code document boolean for need approval."
    )
    requestor_field = fields.Char()
    state_field = fields.Char()
    state_request_approvals = fields.Char(
        default='draft',
        help="State when need approval button",
    )
    state_rejected = fields.Char(
        help="State when reject"
    )
    # state_reject = fields.Char(help="State when reject")
    state_approved = fields.Char(
        help="State when approved. Leve blank when not need update"
    )
    state_canceled = fields.Char(
        help="State when canceled. Leve blank when not need update")
    state_reset_to_draft = fields.Char(
        help="State when state_reset_to_draft. Leve blank when not need update"
    )
    state_waiting_approvals = fields.Char(
        help="Waiting Approval for approval_line"
    )

    # action
    available_action_request_approval = fields.Boolean()
    invoke_validate_request_approval = fields.Char()
    invoke_approval_start = fields.Char()
    invoke_approval_done = fields.Char()

    available_action_approve = fields.Boolean()
    invoke_validate_approve = fields.Char()
    approve_action_type = fields.Selection([
        ('window_action', 'Window Action'),
        ('server_action', 'Server Action'),
        ('method', 'Method'),
    ])
    approve_window_action_id = fields.Many2one('ir.actions.act_window')
    approve_server_action_id = fields.Many2one('ir.actions.server')
    invoke_method_approve = fields.Char()
    invoke_before_approve = fields.Char()
    invoke_after_approve = fields.Char()
    notes_chatter_approved = fields.Boolean("Note Chatter Approve")

    available_action_reject = fields.Boolean()
    invoke_validate_reject = fields.Char()
    reject_action_type = fields.Selection([
        ('window_action', 'Window Action'),
        ('server_action', 'Server Action'),
        ('method', 'Method'),
    ])
    reject_window_action_id = fields.Many2one('ir.actions.act_window')
    reject_server_action_id = fields.Many2one('ir.actions.server')
    invoke_method_reject = fields.Char()
    invoke_before_reject = fields.Char()
    invoke_after_reject = fields.Char()
    notes_chatter_rejected = fields.Boolean("Note Chatter Rejected")

    available_action_cancel = fields.Boolean()
    invoke_validate_cancel = fields.Char()
    cancel_action_type = fields.Selection([
        ('window_action', 'Window Action'),
        ('server_action', 'Server Action'),
        ('method', 'Method'),
    ])
    cancel_window_action_id = fields.Many2one('ir.actions.act_window')
    cancel_server_action_id = fields.Many2one('ir.actions.server')
    invoke_method_cancel = fields.Char()
    invoke_before_cancel = fields.Char()
    invoke_after_cancel = fields.Char()
    notes_chatter_cancel = fields.Boolean("Note Chatter Cancel")

    available_action_reset_to_draft = fields.Boolean()
    invoke_validate_reset_to_draft = fields.Char()
    reset_to_draft_action_type = fields.Selection([
        ('window_action', 'Window Action'),
        ('server_action', 'Server Action'),
        ('method', 'Method'),
    ])
    reset_to_draft_window_action_id = fields.Many2one('ir.actions.act_window')
    reset_to_draft_server_action_id = fields.Many2one('ir.actions.server')
    invoke_method_reset_to_draft = fields.Char()
    invoke_before_reset_to_draft = fields.Char()
    invoke_after_reset_to_draft = fields.Char()
    notes_chatter_reset_to_draft = fields.Boolean("Note Chatter To Draft")

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
    notification_cancel_approver_id = fields.Many2one(
        'notification.template',
        'Notification Cancel To Approver',
        ondelete='set null',
        help="Notification Set to Draft To Approver when requester ."
    )
    notification_reset_to_draft_approver_id = fields.Many2one(
        'notification.template',
        'Notification Set to Draft To Approver',
        ondelete='set null',
        help="Notification Set to Draft To Approver when requester ."
    )
    notification_approved_id = fields.Many2one(
        'notification.template',
        ondelete='set null',
        help="Notification template used for reject notifications."
    )
    notification_rejection_id = fields.Many2one(
        'notification.template',
        ondelete='set null',
        help="Notification template used for reject notifications."
    )
    notification_rejection_to_approver_id = fields.Many2one(
        'notification.template',
        ondelete='set null',
        help="Notification template used aproved accept notification for reject."
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

    @api.depends('approval_task_line_model_id')
    def compute_approval_template_line_id(self):
        for rec in self:
            rec.approval_template_line_id = self.approval_template_line_id.search(
                [('model_id', '=', rec.approval_task_line_model_id.id)], limit=1
            ) or None

    def action_generate_view(self):
        for template in self:
            template._create_or_update_view()

    def remove_generated_view(self):
        self.ensure_one()
        if self.generate_view_id:
            self.generate_view_id.unlink()
            self.generate_view_id = False
        self.generate_field_approval_task_line = False
        if self.generate_field_approval_task_line_id:
            self.generate_field_approval_task_line_id.unlink()
            self.generate_field_approval_task_line_id = False

    def _create_or_update_view(self):
        self.ensure_one()

        vals = {
            "name": "%s Approval Generated" % self.model,
            "type": "form",
            "model": self.model,
            "mode": "extension",
            "inherit_id": self.view_id.id,
            "arch_base": self._generate_arch(),
        }

        if self.generate_view_id:
            self.generate_view_id.write(vals)
            view = self.generate_view_id
        else:
            view = self.env["ir.ui.view"].create(vals)
            self.generate_view_id = view

        return view

    def _generate_arch(self):
        root = etree.Element("data")

        xpath = etree.SubElement(root, "xpath")
        xpath.set("expr", "//header")
        xpath.set("position", "inside")

        field = etree.SubElement(xpath, "field")
        field.set("name", "approval_template_id")
        field.set("invisible", "1")

        field = etree.SubElement(xpath, "field")
        field.set("name", "approval_template_line_id")
        field.set("invisible", "1")

        field = etree.SubElement(xpath, "field")
        field.set("name", "approval_instance_id")
        field.set("invisible", "1")

        field = etree.SubElement(xpath, "field")
        field.set("name", "access_requester")
        field.set("invisible", "1")

        field = etree.SubElement(xpath, "field")
        field.set("name", "access_approval")
        field.set("invisible", "1")

        self._generate_buttons(xpath)
        if self.approval_task_line_page and self.approval_task_line_field:
            xpath = etree.SubElement(root, "xpath")
            xpath.set("expr", "//notebook")
            xpath.set("position", "inside")
            self._generate_approval_page(xpath)

        return etree.tostring(
            root,
            pretty_print=True,
            encoding="unicode",
        )

    def _generate_approval_page(self, parent):
        page = etree.SubElement(parent, "page")
        page.set("name", "page_approval_task_line")
        page.set("string", "Approval")
        page.set("type", "object")

        field = etree.SubElement(page, "field")
        if self.generate_field_approval_task_line and self.generate_field_approval_task_line_id:
            field.set("name", self.generate_field_approval_task_line_id.name)
        else:
            field.set("name", self.approval_task_line_field)
        # field.set("invisible", "1")
        # button.set("context", "{'approval_action':'%s'}" % button_def["action"]

    def _generate_buttons(self, parent):
        """
        Generate approval fields and buttons
        parent: xpath node
        """

        for button_def in APPROVAL_BUTTONS:
            # 'available_action_request',
            # 'available_action_approve',
            # 'available_action_reject',
            # 'available_action_cancel',
            # 'available_action_reset_draft',
            if not getattr(self, "available_action_%s" % button_def["action"], False):
                continue
            # field invisible untuk attrs
            field = etree.SubElement(parent, "field")
            field.set("name", button_def["access_field"])
            field.set("invisible", "1")

            # button
            button = etree.SubElement(parent, "button")
            button.set("name", "approval_action")
            button.set("string", button_def["label"])
            button.set("type", "object")
            button.set("context", "{'approval_action':'%s'}" % button_def["action"])

            if button_def["class"]:
                button.set("class", button_def["class"])

            # visibility berdasarkan access field
            button.set(
                "attrs",
                "{'invisible':[('%s','=',False)]}"
                % button_def["access_field"]
            )

    def _generate_field_compute(self):
        field_name = f"x_approval_task_line_{self.id}"
        compute = """
for rec in self:
    rec['%s'] = rec.approval_template_line_id.get_all_approval_task_line(transaction_object=rec)
""" % field_name
        vals = {
            "name": field_name,
            "field_description": "Approval Task Line",
            "model_id": self.model_id.id,
            "model": self.model,
            "ttype": "many2many",
            "relation": self.approval_task_line_model,
            "state": "manual",
            "depends": "approval_template_line_id",
            "compute": compute,
        }
        if self.generate_field_approval_task_line_id:
            self.generate_field_approval_task_line_id.write(vals)
        else:
            self.generate_field_approval_task_line_id = self.env['ir.model.fields'].create(vals)

    @api.model_create_multi
    @api.returns('self', lambda value: value.id)
    def create(self, vals_list):
        for vals in vals_list:
            if 'state_reject' in vals:
                vals['state_rejected'] = vals.pop('state_reject')

        return super().create(vals_list)

    def write(self, vals):
        if 'state_reject' in vals:
            vals['state_rejected'] = vals.pop('state_reject')
        res = super().write(vals)

        trigger_fields = {
            'view_id',
            'available_action_request',
            'available_action_approve',
            'available_action_reject',
            'available_action_cancel',
            'available_action_reset_to_draft',
            'approval_task_line_field',
            'approval_task_line_page',
            'generate_field_approval_task_line',
        }

        if trigger_fields.intersection(vals):
            if self.generate_field_approval_task_line:
                self._generate_field_compute()
            self.action_generate_view()

        return res

    def unlink(self):
        for rec in self:
            rec.remove_generated_view()

        return super().unlink()

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

    def get_state_request_approvals(self):
        if self.state_request_approvals:
            return self.state_request_approvals.split(',')
        else:
            return ['waiting_approval']

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

    def get_state_rejected(self):
        return self.state_rejected

    def get_state_approved(self):
        return self.state_approved

    def prepare_dict(self):
        return {'model_id': self.model_id.id}

    def get_transaction_status(self, transaction):
        rec = self.ensure_one()
        state_field = rec.get_state_field()
        return transaction and getattr(transaction, state_field)

    def get_user_requestor(self, transaction):
        rec = self.ensure_one()
        requestor = rec.requestor_field or 'create_uid'
        return getattr(transaction, requestor) or transaction.create_uid

    def is_model_need_approval(self, transaction):
        if not self:
            return False

        rec = self.ensure_one()
        if rec.need_approval_mode == 'field':
            return transaction and getattr(transaction, rec.need_approval_field)
        if rec.need_approval_function == 'field':
            try:
                return safe_call_method(transaction, rec.need_approval_function)
            except:
                _logger.exception("Error")
                return False
        if rec.need_approval_mode == 'code':
            try:
                localdict = {
                    'result': False,
                    'transaction_object': transaction,
                }
                safe_eval(rec.need_approval_code, localdict, mode="exec", nocopy=True)
                return "result" in localdict and localdict["result"] or False
            except:
                _logger.exception("Error")
                return False
        return True

    def is_status_request_approval(self, transaction):
        rec = self.ensure_one()
        state_field = rec.get_state_field()
        state_request_approvals = rec.get_state_request_approvals()
        return transaction and getattr(transaction, state_field) in state_request_approvals

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
        if self.approval_matrix_id:
            return self.approval_matrix_id._name
        return default

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
        if not self.reminder_interval_number:
            return False
        nextcall = from_date_time or fields.Datetime.now()
        nextcall += _intervalTypes[self.reminder_interval_type](self.reminder_interval_number)
        return nextcall

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

    @api.model
    def get_approval_template_line(self, **kwargs):
        if self:
            approval_template_line = self[0].approval_template_line_id
        else:
            approval_template_line = self.approval_template_line_id.browse()

        return approval_template_line

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

    def get_company(self, **kwargs):
        company = kwargs.get('company')
        if company and isinstance(company, models.Model):
            return company

        transaction_object = self.get_transaction_object(**kwargs)
        return getattr(transaction_object, 'company_id', None)

    def get_domain_waiting_status(self, **kwargs):
        if not self:
            return []
        approval_template = self.ensure_one()
        domain = []
        waiting_status = approval_template.get_state_waiting_approvals()
        if waiting_status and approval_template.state_field:
            domain = [(approval_template.state_field, 'in', waiting_status)]
        return domain

    def get_next_approval_task_line(self, approval_task_line=None, **kwargs):
        approval_template_line = self.get_approval_template_line(
            approval_task_line=approval_task_line, **kwargs
        )
        domain = approval_template_line.get_domain_waiting_status(approval_task_line, **kwargs)
        if not isinstance(approval_task_line, models.BaseModel):
            approval_task_line = self.env[approval_template_line.model]
        return approval_task_line.search(domain, limit=1)

    def search_template_by_model(self, transaction_model_name):
        if not transaction_model_name:
            self.browse()
        return self.search([('model_id.model', '=', transaction_model_name)], limit=1)

    def search_template_by_approval_task_line_model(self, model_name):
        if not model_name:
            self.browse()
        return self.search([('approval_task_line_model_id.model', '=', model_name)], limit=1)

    def get_approver_data(self, **kwargs):
        approval_template_line = self.get_approval_template_line(**kwargs)
        return approval_template_line.get_approver_data(**kwargs) or {}

    def get_approval_groups_or_users(self, **kwargs):
        return self.get_approver_data(**kwargs)

    def get_users(self, **kwargs):
        approval_template_line = self.get_approval_template_line(**kwargs)
        return approval_template_line.get_users(**kwargs) or self.env['res.users'].browse()

    def get_access_approval(self, **kwargs):
        company = self.get_company(**kwargs)
        users = self.get_users(**kwargs).get_users_for_approval(company=company)
        return bool(self.env.user in users)

    def set_waiting_approval_status(self, transaction_object):
        if transaction_object and self.state_field and self.state_waiting_approvals:
            wa = self.get_state_waiting_approvals()
            transaction_object.write({
                self.state_field: wa[0]
            })
        else:
            raise UserError("Invalid configuration approval")

    def set_approved_status(self, transaction_object, **kwargs):
        if transaction_object and self.state_field and self.state_approved:
            data = dict(kwargs)
            if self.state_field not in data:
                data[self.state_field] = self.state_approved
            else:
                _logger.info("Update %s -> %s | %s ", self.state_field, data.get(self.state_field), self.state_approved)
            transaction_object.write(data)
        else:
            raise UserError("Invalid configuration approval")

    def set_rejected_status(self, transaction_object, **kwargs):
        if transaction_object and self.state_field and self.state_rejected:
            data = dict(kwargs)
            if self.state_field not in data:
                data[self.state_field] = self.state_rejected
            else:
                _logger.info("Update %s -> %s | %s ", self.state_field, data.get(self.state_field), self.state_rejected)
            transaction_object.write(data)
        else:
            raise UserError("Invalid configuration rejected_status")

    def set_reset_to_draft(self, transaction_object, **kwargs):
        if transaction_object and self.state_field and self.state_reset_to_draft:
            transaction_object.write({
                self.state_field: self.state_reset_to_draft
            })
        else:
            raise UserError("Invalid configuration reset_to_draft")

    def set_cancel(self, transaction_object):
        if transaction_object and self.state_field and self.state_reject:
            transaction_object.write({
                self.state_field: self.state_canceled
            })
        else:
            raise UserError("Invalid configuration reset_to_draft")
    def do_approve(self, approval_task_line=None, **kw):
        kw['approval_template'] = self.ensure_one()
        return self.approval_template_line_id.do_approve(approval_task_line, kw)

    def before_approve(self, **kw):
        approval_template = self.ensure_one()
        transaction_object = approval_template.get_transaction_object(**kw)
        approval_template.invoke_method(transaction_object, 'after_approve', kw)
        return kw

    def after_approve(self, **kwargs):
        approval_template = self.ensure_one()
        approval_instance = approval_template.get_approval_instance(**kwargs)
        transaction_object = approval_template.get_transaction_object(**kwargs)
        kw = dict(kwargs)
        kw['skip_send_notification'] = True
        kw['approval_instance'] = approval_instance
        kw['approval_template'] = approval_template
        is_approval_done = kwargs.get('is_approval_done')
        trx_update_value = kwargs.get('transaction_update_value') or {}
        approval_template.invoke_method(transaction_object, 'after_approve', kw)

        if is_approval_done:
            kw['is_approved'] = True
            trx_update_value.update(kwargs.get('update_value') or {})
            approval_template.set_approved_status(transaction_object, **trx_update_value)
            # state_field = approval_template.get_state_field()
            # state_approved = approval_template.get_state_approved()
            # if state_approved and state_field not in trx_update_value:
            #     trx_update_value[state_field] = state_approved
        elif trx_update_value:
            _logger.info("Info Update state %s ", trx_update_value)
            transaction_object.write(trx_update_value)

        if is_approval_done or not approval_template.is_status_waiting_approval(transaction_object):
            kw['is_approval_done'] = True
            kw['is_approved'] = True
            approval_template.done_approval(**kw)
        else:
            kw['is_approval_done'] = False
            kw['skip_send_notification'] = False
            kw['request_approval_task_date'] = fields.Datetime.now()
            approval_instance.register_approval_task_line(**kw)

        kw_approved = dict(kwargs)
        kw_approved.update(
            skip_send_notification=False,
            approval_template=approval_template,
            approval_instance=approval_instance,
            transaction_id=approval_instance.transaction_id,
            transaction_model_name=approval_instance.transaction_model_name,
        )

        notes_chatter = False
        notification = self.notification_approved_id
        if notification:
            requestor = self.get_user_requestor()
            notification.send_notification_to_users(requestor, transaction_object.id, **kw_approved)
            notes_chatter = notification.notes_chatter

        if not notes_chatter and self.notes_chatter_approved:
            if have_method(transaction_object, 'get_approved_message'):
                approved_message = safe_call_method(
                    transaction_object, "get_approved_message", kwargs=kw_approved
                )
            else:
                approved_message = self.get_approved_message(**kw)
            approved_message and self.notification_approved_id.send_message_post(transaction_object,approved_message)
        return kw

    def get_approved_message(self, **kwargs):
        return _("%s has approved this request") % (self.env.user.name)

    def do_reject(self, approval_task_line=None, **kw):
        kw['approval_template'] = self.ensure_one()
        return self.approval_template_line_id.do_reject(approval_task_line, kw)

    def before_reject(self, **kw):
        approval_template = self.ensure_one()
        transaction_object = approval_template.get_transaction_object(**kw)
        approval_template.invoke_method(transaction_object, 'before_reject', kw)
        return kw

    def after_reject(self, **kwargs):
        if not self:
            _logger.warning("No Instance for After Reject")
            return self
        approval_template = self.ensure_one()
        approval_instance = approval_template.get_approval_instance(**kwargs)
        transaction_object = approval_template.get_transaction_object(**kwargs)
        kw = dict(kwargs)
        kw['skip_send_notification'] = True
        kw['approval_instance'] = approval_instance
        kw['approval_template'] = approval_template
        # kw['notification_template'] = notification_template
        # transaction_object = approval_instance.get_transaction_object()
        is_approval_done = kwargs.get('is_approval_done')
        trx_update_value = kwargs.get('transaction_update_value') or {}

        approval_template.invoke_method(transaction_object, 'after_reject', kw)
        if is_approval_done:
            kw['is_rejected'] = True
            trx_update_value.update(kwargs.get('update_value') or {})
            approval_template.set_rejected_status(transaction_object, **trx_update_value)
            # state_field = approval_instance.get_state_field()
            # state_rejected = approval_instance.get_state_rejected()
            # if state_rejected and state_field not in trx_update_value:
            #     trx_update_value[state_field] = state_rejected
        elif trx_update_value:
            transaction_object.write(trx_update_value)
            _logger.info("No update state %s", trx_update_value)

        if is_approval_done or not approval_template.is_status_waiting_approval(transaction_object):
            kw['is_approval_done'] = True
            kw['is_rejected'] = True
            approval_template.done_approval(**kw)
        else:
            kw['is_approval_done'] = False
            kw['skip_send_notification'] = False
            kw['request_approval_task_date'] = fields.Datetime.now()
            kw['approval_task_line'] = kw.get(
                'approval_task_line_next') or approval_template.get_next_approval_task_line()
            approval_instance.register_approval_task_line(**kw)

        kw_rejected = dict(kwargs)
        kw_rejected.update(
            approval_template=approval_template,
            approval_instance=approval_instance,
            transaction_id=approval_instance.transaction_id,
            transaction_model_name=approval_instance.transaction_model_name,
        )
        notes_chatter = False
        notification = self.notification_rejection_id
        if notification:
            requestor = self.get_user_requestor()
            notification.send_notification_to_users(requestor, transaction_object.id, **kw_rejected)
            notes_chatter = notification.notes_chatter
        if not notes_chatter and self.notes_chatter_approved:
            if have_method(transaction_object, 'get_rejected_message'):
                rejected_message = safe_call_method(
                    transaction_object, "get_rejected_message", kwargs=kw_rejected
                )
            else:
                rejected_message = self.get_rejected_message(**kw)
            rejected_message and self._mail_message_approve(rejected_message)

        approval_task_task_between = kw.get('approval_task_task_between')
        notification = self.notification_rejection_to_approver_id
        if self.notification_rejection_to_approver_id and approval_task_task_between:
            approval_template_line = self.get_approval_template_line(**kwargs)
            user_ids = approval_template_line.get_user_execution(approval_task_task_between)
            notification.send_notification_to_users(user_ids, transaction_object.id, **kw_rejected)

        return kw

    def do_cancel(self, **kw):
        kw['approval_template'] = self.ensure_one()
        kw['approval_template_line'] = approval_template_line = self.get_approval_template_line(**kw)
        kw['transaction_object'] = transaction_object = self.get_transaction_object(**kw)
        self.before_cancel(*kw)
        state_approved = approval_template_line.get_state_approved()
        kw['approval_task_line_approved'] = approval_template_line.get_all_approval_task_line(state_approved, **kw)

        if self.cancel_action_type == 'method':
            safe_call_method(transaction_object, self.invoke_method_cancel, kwargs=kw)
        else:
            self.set_cancel(transaction_object)
        kw['is_cancel'] = True
        kw['is_approval_done'] = True
        self.after_cancel(*kw)
        audit_log = dict(kw)
        self.env['approval.audit.log'].create_approval_audit_log_canceled(**audit_log)
        return kw

    def before_cancel(self, **kw):
        approval_template = self.ensure_one()
        transaction_object = approval_template.get_transaction_object(**kw)
        approval_template.invoke_method(transaction_object, 'before_cancel', kw)
        return kw

    def after_cancel(self, **kw):
        transaction_object = self.get_transaction_object(**kw)
        notes_chatter = False
        notification = self.notification_cancel_approver_id
        if notification:
            approval_template_line = self.get_approval_template_line(**kw)
            kwr = dict(kw)
            approval_task_line_approved = kw.get('approval_task_line_approved')
            kwr['approval_task_line'] = approval_task_line_approved
            users_ids = approval_template_line.get_user_execution(**kwr)
            notification.send_notification_to_users(users_ids, transaction_object.id, **kw)
            notes_chatter = notification.notes_chatter
        if not notes_chatter and self.notes_chatter_approved:
            pass
        self.done_approval(**kw)

        # approval_instance = self.get_approval_instance(**kw)
        notes_chatter = False
        # approval_instance.after_cancel(**kw)
        notification = self.notification_cancel_approver_id
        if notification:
            notes_chatter = notification.notes_chatter
            pass
        if not notes_chatter and self.notes_chatter_approved:
            pass

        return kw

    def do_reset_to_draft(self, **kw):
        kw['approval_template'] = self.ensure_one()
        kw['approval_template_line'] = approval_template_line = self.get_approval_template_line(**kw)
        kw['transaction_object'] = transaction_object = self.get_transaction_object(**kw)
        self.before_reset_to_draft(**kw)
        state_approved = approval_template_line.get_state_approved()
        kw['approval_task_line_approved'] = approval_template_line.get_all_approval_task_line(state_approved, **kw)
        if self.cancel_action_type == 'method':
            safe_call_method(transaction_object, self.invoke_method_reset_to_draft, kwargs=kw)
        else:
            self.set_reset_to_draft(transaction_object)
        kw['is_reset_to_draft'] = True
        self.after_reset_to_draft(**kw)
        audit_log = dict(kw)
        self.env['approval.audit.log'].create_approval_audit_log_reset(**audit_log)
        return kw

    @api.model
    def before_reset_to_draft(self, **kw):
        approval_template = self.ensure_one()
        transaction_object = approval_template.get_transaction_object(**kw)
        approval_template.invoke_method(transaction_object, 'before_reset_to_draft', kw)
        # approval_instance = self.get_approval_instance(**kw)
        # approval_instance.before_reset_to_draft(**kw)
        return kw

    def after_reset_to_draft(self, **kw):
        transaction_object = self.get_transaction_object(**kw)
        notes_chatter = False
        notification = self.notification_reset_to_draft_approver_id
        approval_template_line = self.get_approval_template_line(**kw)
        if notification:
            kwr = dict(kw)
            approval_task_line_approved = kw.get('approval_task_line_approved')
            kwr['approval_task_line'] = approval_task_line_approved
            users_ids = approval_template_line.get_user_execution(**kwr)
            notification.send_notification_to_users(users_ids, transaction_object.id)
            notes_chatter = notification.notes_chatter
        if not notes_chatter and self.notes_chatter_approved:
            pass
        self.done_approval(**kw)
        return kw

    @api.model
    def get_rejected_message(self, **kwargs):
        reason = kwargs.get('reason')
        return _('Note Reject => %s') % reason

    def done_approval(self, **kwargs):
        if not self:
            _logger.warning("No Template for done Approval")
            return self

        approval_template = self.ensure_one()
        approval_instance = self.get_approval_instance(**kwargs)
        kw = dict(kwargs)
        transaction_object = self.get_transaction_object(**kw)
        safe_call_method(transaction_object, approval_template.invoke_approval_done, kwargs=kw)
        approval_instance.unregister_approval_task_line(**kwargs)
        if approval_template.is_status_waiting_approval(transaction_object):
            if kwargs.get('is_approved'):
                _logger.warning("Status is waiting_approval try force set done")
                approval_template.set_approved_status(transaction_object)
            elif kwargs.get('is_reset_to_draft'):
                approval_template.set_reset_to_draft(transaction_object)

    def clear_approval(self, **kwargs):
        if not self:
            _logger.warning("No Template for celar Approval")
            return self
        rec = self.ensure_one()
        approval_template_line = rec.get_approval_template_line(**kwargs)
        if not approval_template_line:
            _logger.warning("No Template Line for celar Approval")
            return self
        approval_template_line.clear_approval(**kwargs)
        return self


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

    def migrate_approval_task(self, raise_exception=True, skip_send_notification=True, reset_reminder=False,
                              reset_request_approval_task_date=False):
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
                            skip_send_notification=skip_send_notification,
                            reset_reminder=reset_reminder,
                            reset_request_approval_task_date=reset_request_approval_task_date,
                        )

                        transaction_ids.append(rec.transaction_id)
                        approval_audit_log = env['approval.audit.log'].search([
                            ('create_date', '>', rec.request_approval_task_date),
                            ('transaction_model_name', '=', rec.transaction_model_name),
                            ('transaction_id', '=', rec.transaction_id),
                        ], limit=1, order='create_date desc')
                        # chek jika ada action yang tecatat
                        if approval_audit_log:
                            rec.sudo().write({'request_approval_task_date': approval_audit_log.create_date})
                        if template.reminder_interval_number > 0:
                            if not rec.reminder_next_datetime:
                                reminder_next_datetime = template.get_next_reminder_datetime(
                                    rec.reminder_last_datetime or rec.request_approval_task_date
                                )
                                rec.sudo().write({'reminder_next_datetime': reminder_next_datetime})
                        else:
                            # jika 0 maka remainder disable
                            rec.reminder_next_datetime = False
                        # chek last action
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
                    approval_instance.register_approval_task_line(
                        skip_send_notification=skip_send_notification,
                        reset_reminder=reset_reminder,
                        reset_request_approval_task_date=reset_request_approval_task_date,
                    )
                    transaction_ids.append(rec.id)
                except:
                    _logger.exception("register_approval_task_line 2")
                    if raise_exception:
                        raise
            # remove not active instance
            # instances = env['approval.instance'].search(
            #     [('transaction_model_name', '=', model), ('id', 'not in', transaction_ids)]
            # )
            # for instance in instances:
            #     if instance.id in transaction_ids:
            #         instance.unlink()
