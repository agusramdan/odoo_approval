# -*- coding: utf-8 -*-

import base64
import logging

from lxml import etree
from dateutil.relativedelta import relativedelta
import odoo
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare
from odoo.tools.safe_eval import safe_eval, test_python_expr
from pytz import timezone
from ..tools.utils import have_method, safe_call_method

_logger = logging.getLogger(__name__)

DEFAULT_CODE = """
# Available variables:
#  - transaction_object 
#----------------------
result = transaction_object.move_type == 'in_invoice'
"""

"""
Di odoo ada 1 model mempunyai lebih dar 1 istilah yang berbeda contoh:

account.move

Bisa jadi 

- Vendor bill
- Costumer Invoice

"""

DEFAULT_PDF_PYTHON_CODE = """
# Mapping crate PDF Document for sing
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
# requester = approval_instance.requester_id
# signature_ids = [{
#   'name':'signature_requester',
#   'user_id':requester.id,
#   'user_email':requester.email,
#   'placeholder':"[[signature_requester_placeholder]]",
#   'auto_sign_after_request':True
# }]
# approval_task_line = approval_instance.get_all_approval_task_line()
# if approval_task_line:
#   for apr in approval_task_line:
#     signature_ids.append({
#       'name':'signature_approvar_%s'%apr.id,
#       'placeholder': "[[signature_approvar_%s_placeholder]]"%apr.id,
#       'source_model': apr._name,
#       'source_res_id': apr.id,
#     })
# response = {
#   'name':transaction_object.name,
#   'template_id':1,
#   'source_model': approval_instance.transaction_model_name,
#   'source_res_id': approval_instance.transaction_id,
#   'pdf_file': transaction_object.file_approve,
#   'pdf_filename':transaction_object.file_approve_name,
#   'signature_ids': signature_ids,
# }
\n\n\n\n
"""
DEFAULT_PDF_SIGN_PYTHON_CODE = """
# Mapping approval to pdf sign
# Available variables:
#  - approval_instance
#  - transaction_object 
#  - approval_task_line 
#  - user_execution
# To return an response, assign: response = {...}

# response={
#   'source_model': approval_task_line._name,
#   'source_res_id': approval_task_line.id,
#   'user_execution': user_execution,
#   'user_execution_id': user_execution.id,
#   'user_execution_email': user_execution.email,
#   'user_execution_name': user_execution.name,
#   'auto_sign_ca': True,
}
\n\n\n\n
"""

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
        "class": "btn-danger",
    },
    {
        "action": "cancel",
        "label": "Cancel",
        "access_field": "access_cancel_action",
        "class": "btn-danger",
    },
    {
        "action": "reset_to_draft",
        "label": "Reset To Draft",
        "access_field": "access_reset_to_draft_action",
        "class": None,
    },
    {
        "action": "show_sign_pdf",
        "label": "Show Sign PDF",
        "access_field": "access_show_sign_pdf_action",
        "class": None,
    },
]


class ApprovalDocument(models.Model):
    _name = 'approval.document'
    _description = "Document Model Register"
    _rec_name = 'name'
    _order = 'priority,id'
    _sql_constraints = [
        ('document_code_unique', 'unique(code)', 'Document Code must be uniq!')
    ]

    code = fields.Char(required=True)
    name = fields.Char(required=True)
    priority = fields.Integer(default=20)
    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade', )
    model = fields.Char(related='model_id.model')
    generate_field_approval_task_line = fields.Boolean()
    generate_field_approval_task_line_id = fields.Many2one(
        'ir.model.fields',
        'Generate x_document_approval_task_line_',
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
    # approval_mode = fields.Selection([
    #     ('matrix', 'Approval Matrix'),
    #     ('model', 'Responsible'),
    # ])
    approval_matrix_id = fields.Many2one(
        "approval.matrix.rule", string="Approval Matrix", ondelete='set null',
    )
    # approval_matrix_model = fields.Char()
    # approval_matrix_model_id = fields.Many2one('ir.model', string="Target Model", ondelete='set null', )
    # approval_responsible_id = fields.Many2one('approval.responsible', string="Responsible Model", ondelete='set null', )
    # # approval.task.line.mixin
    approval_template_id = fields.Many2one(
        'approval.template',
        compute="_compute_approval_template_id"
    )
    approval_template_line_id = fields.Many2one(
        'approval.template.line',
        compute="_compute_approval_template_id"
    )
    # approval_task_line_model_id = fields.Many2one('ir.model', ondelete='set null', )
    # approval_task_line_model = fields.Char(
    #     related='approval_task_line_model_id.model'
    # )
    approval_banner_show = fields.Boolean("Approval Banner")
    approval_task_line_page = fields.Boolean("Approval Page")
    approval_task_line_field = fields.Char('Line Field')

    # approval_template_line_id = fields.Many2one(
    #     'approval.template.line', compute='compute_approval_template_line_id',
    # )
    # available_approval_template_line_models_ids = fields.Many2many(
    #     'ir.model',
    #     compute='_compute_available_approval_template_line_models_ids'
    # )

    need_approval = fields.Boolean()
    condition_select = fields.Selection(
        [("none", "Always True"), ("python", "Python Expression"), ],
        string="Condition Based on",
        default="none",
        required=True,
    )
    condition_python = fields.Text(
        string="Python Condition",
        required=True,
        default=DEFAULT_CODE,
        help="Applied this rule for calculation if condition is true. You can "
             "specify condition like transaction_object.move_type == 'out_invoice' ",
    )
    pdf_code = fields.Text(
        string='Python Code',
        default=DEFAULT_PDF_PYTHON_CODE,
        help="Write Python code that the action will execute. Some variables are "
             "available for use; help about python expression is given in the help tab."
    )
    pdf_sign_code = fields.Text(
        string='PDF Sign Code',
        default=DEFAULT_PDF_SIGN_PYTHON_CODE,
        help="Write Python code that the action will execute. Some variables are "
             "available for use; help about python expression is given in the help tab."
    )
    pdf_sign_server = fields.Selection([('local', 'Local'), ('remote', 'Remote')], default='local')
    pdf_sign = fields.Selection(
        [('none', 'None'),
         ('approve_is_sign_pdf', 'Approve is Sign PDF'),
         ('approve_form_sign_pdf', 'Sign PDF is Approve'),
         ],
        default='none',
        help="""
        none : Not related pdf sign
        Approve is Sign PDF: When approve this instance will propagate to sign pdf (internal user only).
        Sign PDF is Approve: Sign document will approve this instance when approve will redirect to sign authenticate.
        """
    )
    document_select = fields.Selection([
        ('const', 'Const'),
        ('field', 'Field'),
        ('function', 'Function'),
    ])
    document_const = fields.Char(help="Document Const")
    document_field = fields.Char(help="Document Field")
    document_function = fields.Char(help="Document Function")

    number_select = fields.Selection([
        ('field', 'Field'),
        ('function', 'Function'),
    ])
    number_field = fields.Char(help="Number Field")
    number_function = fields.Char(help="Number Function")

    description_select = fields.Selection([
        ('const', 'Const'),
        ('field', 'Field'),
        ('function', 'Function'),
    ])
    description_const = fields.Char(help="Description Const")
    description_field = fields.Char(help="Description Field")
    description_function = fields.Char(help="Description Function")

    requestor_select = fields.Selection([
        ('field', 'Field'),
        ('function', 'Function'),
    ])
    requestor_const = fields.Char(help="Requestor Const")
    requestor_field = fields.Char(help="Requestor Field")
    requestor_function = fields.Char(help="Requestor Function")

    available_action_request_approval = fields.Boolean('Request Approval')
    available_action_approve = fields.Boolean('Approve')
    available_action_reject = fields.Boolean('Reject')
    available_action_cancel = fields.Boolean('Cancel')
    available_action_reset_to_draft = fields.Boolean('Reset to Draft')
    available_action_show_sign_pdf = fields.Boolean('Show Sign PDF')

    requestor_group_ids = fields.Many2many('res.groups', help="Requestor Allow Create Approval")

    # def _compute_available_approval_template_line_models_ids(self):
    #     for rec in self:
    #         template_lines = self.approval_template_line_id.search([])
    #         rec.available_approval_template_line_models_ids = template_lines.model_id
    # @api.depends('approval_task_line_model_id')
    # def compute_approval_template_line_id(self):
    #     for rec in self:
    #         rec.approval_template_line_id = self.approval_template_line_id.search(
    #             [('model_id', '=', rec.approval_task_line_model_id.id)], limit=1
    #         ) or None

    @api.depends('model_id')
    def _compute_approval_template_id(self):
        for rec in self:
            rec.approval_template_id = self.approval_template_id.search_template_by_model(rec.model_id.model)
            rec.approval_template_line_id = rec.approval_template_id.approval_template_line_id

    def get_data_object(self, data_type, transaction_object, params=None, raise_exception=True):
        data_select = getattr(self, f"{data_type}_select", "")
        if not data_select:
            return None
        data_target = getattr(self, f"{data_type}_{data_select}", "")
        if data_select == 'const':
            return data_target

        if not data_target:
            return None

        if data_select == 'field':
            return transaction_object and getattr(transaction_object, data_target)
        if data_select == 'function':
            try:
                return safe_call_method(transaction_object, data_target)
            except:
                if raise_exception:
                    _logger.error("Function error , %s , %s ", self, transaction_object)
                    raise
                _logger.exception("Error")
                return False
        if data_select == 'code':
            try:
                localdict = {
                    'result': False,
                    'transaction_object': transaction_object,
                    'approval_document': self,
                    'params': params,
                }
                safe_eval(data_target, localdict, mode="exec", nocopy=True)
                return "result" in localdict and localdict["result"] or False
            except:
                if raise_exception:
                    _logger.error("Code error , %s , %s ", self, transaction_object)
                    raise
                _logger.exception("Error")
                return False
        return False

    def get_internal_number(self, transaction_object):
        return self.get_data_object('number', transaction_object, raise_exception=False)

    def get_internal_document(self, transaction_object):
        return self.get_data_object('document', transaction_object, raise_exception=False)

    def get_internal_description(self, transaction_object):
        return self.get_data_object('description', transaction_object, raise_exception=False)

    def get_internal_requestor(self, transaction_object):
        return self.get_data_object('requestor', transaction_object, raise_exception=False) or self.env['res.users']

    def write(self, vals):
        if 'state_request_approval' in vals:
            vals['state_request_approvals'] = vals.pop('state_request_approval')
        if 'state_reject' in vals:
            vals['state_rejected'] = vals.pop('state_reject')
        res = super().write(vals)
        if self.env.context.get('___generate_field_approval_task_line'):
            trigger_fields = {
                'view_id',
                'available_action_request',
                'available_action_approve',
                'available_action_reject',
                'available_action_cancel',
                'available_action_reset_to_draft',
                'available_action_show_sign_pdf',
                'approval_banner_show',
                'approval_task_line_page',
                'approval_task_line_field',
            }
            if trigger_fields.intersection(vals):
                for template in self:
                    if template.view_id and template.generate_view_id:
                        if template.generate_field_approval_task_line:
                            template._generate_field_compute()
                        template.action_generate_view()
                    elif not template.view_id and template.generate_view_id:
                        template.remove_generated_view()

        return res

    def action_generate_view(self):
        for template in self:
            if self.view_id:
                template._create_or_update_view()

    def remove_generated_view(self):
        self.ensure_one()
        if self.generate_view_id:
            self.generate_view_id.unlink()
            self.generate_view_id = False

    def _create_or_update_view(self):
        self.ensure_one()
        vals = {
            "name": "%s - %s - Approval Generated" % (self.code, self.name),
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
        field.set("name", "approval_document_id")
        field.set("invisible", "1")

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

        field = etree.SubElement(xpath, "field")
        field.set("name", "is_waiting_approval")
        field.set("invisible", "1")

        field = etree.SubElement(xpath, "field")
        field.set("name", "is_request_approval")
        field.set("invisible", "1")


        self._generate_buttons(xpath)
        if (
                self.approval_task_line_page and
                (
                        (not self.generate_field_approval_task_line and self.approval_task_line_field) or
                        (self.generate_field_approval_task_line and self.generate_field_approval_task_line_id)
                )
        ):
            xpath = etree.SubElement(root, "xpath")
            xpath.set("expr", "//notebook")
            xpath.set("position", "inside")
            self._generate_approval_page(xpath)

        if self.approval_banner_show:
            xpath = etree.SubElement(root, "xpath")
            xpath.set("expr", "//header")
            xpath.set("position", "after")
            self._generate_approval_banner_show(xpath)

        return etree.tostring(
            root,
            pretty_print=True,
            encoding="unicode",
        )

    def _generate_approval_banner_show(self, parent):

        # Waiting approval banner
        banner = etree.SubElement(
            parent,
            "div",
            {
                "class": "alert alert-info",
                "role": "alert",
                "attrs": "{'invisible': ['|', "
                         "('is_waiting_approval', '=', False), "
                         "('flag_reject', '=', True)]}",
            },
        )

        table = etree.SubElement(
            banner,
            "table",
            {"width": "100%"},
        )

        tr = etree.SubElement(table, "tr")

        td = etree.SubElement(
            tr,
            "td",
            {"width": "98%"},
        )

        etree.SubElement(
            td,
            "field",
            {
                "name": "alert_waiting_approval",
                "readonly": "1",
            },
        )

        td = etree.SubElement(tr, "td")

        close = etree.SubElement(
            td,
            "a",
            {
                "class": "close",
                "data-bs-dismiss": "alert",
                "href": "#",
            },
        )

        close.text = "x"

        # Reject banner
        banner = etree.SubElement(
            parent,
            "div",
            {
                "class": "alert alert-danger",
                "role": "alert",
                "attrs": "{'invisible': [('flag_reject', '=', False)]}",
            },
        )

        table = etree.SubElement(
            banner,
            "table",
            {"width": "100%"},
        )

        tr = etree.SubElement(table, "tr")

        td = etree.SubElement(
            tr,
            "td",
            {"width": "98%"},
        )

        etree.SubElement(
            td,
            "field",
            {
                "name": "note_reject",
                "readonly": "1",
            },
        )

        td = etree.SubElement(tr, "td")

        close = etree.SubElement(
            td,
            "a",
            {
                "class": "close",
                "data-bs-dismiss": "alert",
                "href": "#",
            },
        )

        close.text = "x"

        # Hidden helper field
        etree.SubElement(
            parent,
            "field",
            {
                "name": "flag_reject",
                "invisible": "1",
            },
        )

    def _generate_approval_page(self, parent):
        page = etree.SubElement(parent, "page")
        page.set("name", "page_approval_task_line")
        page.set("string", "Approval")
        page.set("type", "object")

        field = etree.SubElement(page, "field")
        if self.generate_field_approval_task_line and self.generate_field_approval_task_line_id:
            field.set("name", self.generate_field_approval_task_line_id.name)
        elif self.approval_task_line_field:
            field.set("name", self.approval_task_line_field)
        # field.set("invisible", "1")
        # button.set("context", "{'approval_action':'%s'}" % button_def["action"]

        def _generate_field_compute(self):
            field_name = f"x_document_approval_task_line_{self.id}"
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
            if not self.generate_field_approval_task_line_id:
                self.generate_field_approval_task_line_id = self.env['ir.model.fields'].search(
                    [('name','=',field_name),('model_id','=',self.model_id.id),]
                )
            if self.generate_field_approval_task_line_id:
                self.generate_field_approval_task_line_id.write(vals)
            else:
                self.generate_field_approval_task_line_id = self.env['ir.model.fields'].create(vals)


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

    def get_approval_document(self, transaction_object):
        if isinstance(transaction_object, models.Model):
            records = self.search([('model_id.model', '=', transaction_object._name)])
            if transaction_object:
                for rec in records:
                    try:
                        if rec.is_satisfy_condition({'transaction_object': transaction_object}):
                            return rec
                    except Exception:
                        _logger.exception("Condition error skip document %s .", rec)
            if records:
                return records[-1]
        return self.browse()

    def is_satisfy_condition(self, localdict):
        self.ensure_one()
        if self.condition_select == "none":
            return True
        elif self.condition_select == 'python':  # python code
            try:
                safe_eval(self.condition_python, localdict, mode="exec", nocopy=True)
                return "result" in localdict and localdict["result"] or False
            except Exception:
                raise UserError(
                    _("Wrong python condition defined for rule %s.")
                    % self.display_name
                )
        else:
            return False

    @api.constrains('condition_python')
    def _check_python_code(self):
        for action in self.sudo().filtered(lambda r: r.condition_select == 'python' and r.condition_python):
            msg = test_python_expr(expr=action.condition_python.strip(), mode="exec")
            if msg:
                raise ValidationError(msg)

    def get_document_for_transaction(self, transaction_model_name, transaction_id):
        transaction_object = self.env[transaction_model_name].browse(transaction_id).exists()
        return self.get_approval_document(transaction_object)

    @api.model
    def _get_pdf_eval_context(self, approval_instance):
        """ evaluation context to pass to safe_eval """
        transaction_object = approval_instance and approval_instance.get_transaction_object()
        approval_document = approval_instance and approval_instance.approval_document_id
        approval_template = approval_instance and approval_instance.approval_template_id

        return {
            'env': self.env,
            'uid': self._uid,
            'user': self.env.user,
            'ref': self.env.ref,
            'Warning': odoo.exceptions.Warning,
            'timezone': timezone,
            'float_compare': float_compare,
            'b64encode': base64.b64encode,
            'b64decode': base64.b64decode,
            'approval_template': approval_template,
            'approval_instance': approval_instance,
            'approval_document': approval_document,
            'transaction_object': transaction_object,
            'transaction_model_name': self.model,
            'transaction_id': transaction_object.id,
        }

    @api.constrains('pdf_code')
    def _check_python_pdf_code(self):
        for action in self.sudo().filtered('pdf_code'):
            msg = test_python_expr(expr=action.pdf_code.strip(), mode="exec")
            if msg:
                raise ValidationError(msg)

    def _run_action_pdf_code_multi(self, eval_context):
        safe_eval(self.pdf_code.strip(), eval_context, mode="exec", nocopy=True)  # nocopy allows to return 'action'
        return eval_context.get('response')

    def get_config_pdf_document(self, approval_instance):
        _logger.info("call create_or_update_pdf_document")
        return self._run_action_pdf_code_multi(self._get_pdf_eval_context(approval_instance))

    @api.model
    def _get_pdf_sign_eval_context(self, approval_instance, approval_task_line, user_execution):
        """ evaluation context to pass to safe_eval """
        eval_context = self._get_pdf_eval_context(approval_instance)
        eval_context['approval_task_line'] = approval_task_line
        eval_context['user_execution'] = user_execution
        return eval_context

    def _run_action_pdf_sign_code_multi(self, eval_context):
        safe_eval(self.pdf_sign_code.strip(), eval_context, mode="exec", nocopy=True)  # nocopy allows to return 'action'
        return eval_context.get('response')

    def get_config_pdf_sign_document(self, approval_instance, approval_task_line,user_execution):
        return self._run_action_pdf_sign_code_multi(
            self._get_pdf_sign_eval_context(approval_instance,approval_task_line,user_execution)
        )
