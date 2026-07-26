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

DEFAULT_CODE = """
# Available variables:
#  - transaction_object 
#----------------------
result = transaction_object.move_type == 'in_invoice'
"""

"""
Di odoo ada 1 model mempunyai lebih dar 1 istilah yang berbeda contoh:

account.move

Visa jadi 

- Vendor bill
- Costumer Invoice

"""


class ApprovalDocument(models.Model):
    _name = 'approval.document'
    _description = "Document Model Register"
    _rec_name = 'model'
    _order = 'priority,id'
    _sql_constraints = [
        ('document_code_unique', 'unique(code)', 'Document Code must be uniq!')
    ]

    code = fields.Char(required=True)
    name = fields.Char(required=True)
    priority = fields.Integer(default=20)
    model_id = fields.Many2one('ir.model', required=True, )
    model = fields.Char(related='model_id.model')
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

    def get_approval_document(self, transaction_object):
        if isinstance(transaction_object, models.Model):
            records = self.search([('model_id.model', '=', transaction_object._name)])
            if transaction_object:
                for rec in records:
                    if rec.is_satisfy_condition({'transaction_object': transaction_object}):
                        return rec
            elif records:
                return records[0]
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
