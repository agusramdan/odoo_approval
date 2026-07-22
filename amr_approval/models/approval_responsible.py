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
#  - responsible_object 
#----------------------
result = responsible_object.acting_manager_id or responsible_object.manager_id
"""


class ApprovalResponsible(models.AbstractModel):
    _name = 'approval.responsible'
    _description = "responsible mapping"
    _rec_name = 'model_id'
    _sql_constraints = [
        ('model_id_unique', 'unique(model_id)', 'Model must be uniq!')
    ]
    model_id = fields.Many2one('ir.model')
    model = fields.Char(related='model_id.model')

    user_mode = fields.Selection([
        ('field', 'Field'),
        ('function', 'Function'),
        ('code', 'Code'),
    ], default='field', required=True)
    user_field = fields.Char(
        help="Filed document boolean for need approval."
    )
    user_function = fields.Char(
        help="Code document boolean for need approval."
    )
    user_code = fields.Text(
        default=DEFAULT_CODE,
        help="Code document boolean for need approval."
    )

    def get_user(self, responsible_object, raise_exception=False, **kwargs):
        if not isinstance(responsible_object, models.Model):
            if raise_exception:
                raise ValueError("Invalid Responsible Object")
            return False
        model_name = responsible_object._name
        rec = self.search([('model_id.model', '=', model_name)])
        if not rec:
            if raise_exception:
                raise ValueError()
        if rec.need_approval_mode == 'field':
            return responsible_object and getattr(responsible_object, rec.user_field)
        if rec.need_approval_function == 'field':
            try:
                return safe_call_method(responsible_object, rec.user_function)
            except:
                if raise_exception:
                    raise
                _logger.exception("Error")
                return False
        if rec.need_approval_mode == 'code':
            try:
                localdict = {
                    'result': False,
                    'responsible_object': responsible_object,
                    'kwargs': kwargs,
                }
                safe_eval(rec.user_code, localdict, mode="exec", nocopy=True)
                return "result" in localdict and localdict["result"] or False
            except:
                if raise_exception:
                    raise
                _logger.exception("Error")
                return False
        return False
