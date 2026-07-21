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
from types import MappingProxyType

_logger = logging.getLogger(__name__)

DEFAULT_CODE = """
# Available variables:
#  - responsible_object 
#  - approval_responsible
#  - params
#----------------------
result = responsible_object.acting_manager_id or responsible_object.manager_id
"""


class ApprovalResponsible(models.Model):
    _name = 'approval.responsible'
    _description = "responsible user for approval"
    _rec_name = 'model_id'
    _sql_constraints = [
        ('model_id_unique', 'unique(model_id)', 'Model must be uniq!')
    ]
    model_id = fields.Many2one('ir.model')
    model = fields.Char(related='model_id.model')
    responsible_type = fields.Selection(
        [
            ('hierarchy', 'Hierarchy'),
            ('representative', 'Representative'),
            ('sequence', 'Sequence'),
            ('grouping', 'Grouping')
        ]
    )
    responsible_select = fields.Selection([
        ('field', 'Field'),
        ('function', 'Function'),
        ('code', 'Code'),
    ], default='field', required=True)
    responsible_field = fields.Char(
        help="Filed document boolean for need approval."
    )
    responsible_function = fields.Char(
        help="Function for need approval."
    )
    responsible_code = fields.Text(
        default=DEFAULT_CODE,
        help="Code document boolean for need approval."
    )
    # when select hierarchy to get user representative
    representative_id = fields.Many2one('approval.responsible')

    approval_task_line_select = fields.Selection([
        ('standard', 'Standard'),
        ('code', 'Code'),
    ], default='standard', required=True)
    approval_task_line_field = fields.Char()
    approval_task_line_code = fields.Text(
        default=DEFAULT_CODE,
        help="Code document boolean for need approval."
    )

    @api.model
    def to_users(self, responsible_object):
        if responsible_object and isinstance(responsible_object, models.Model):
            if responsible_object._name == 'hr.department':
                responsible_object = responsible_object.manager_id
            if responsible_object._name == 'hr.employee':
                responsible_object = responsible_object.user_id
            if responsible_object._name == 'res.groups':
                responsible_object = responsible_object.users
            if responsible_object._name == 'res.users':
                return responsible_object

        return self.env['res.users'].browse()

    def get_next_responsible(self, responsible_object, params=None):
        """hierarchy can get next reponsible"""
        return self._run_definition(responsible_object, params=params)

    def get_user_representative(self, responsible_object, params=None):
        if self.responsible_type == 'representative':
            result = self._run_definition(responsible_object)
        elif self.responsible_type == 'hierarchy':
            responsible_object_next = self.get_next_responsible(responsible_object, params=params)
            result = self.get_user_representative(responsible_object_next)
        else:
            return self.env['res.users'].browse()
        return self.to_users(result) or self.env['res.users'].browse()

    def get_approval_task_line_definition(self, responsible_object, params=None):
        # Return list of dictionary
        if self.responsible_type == 'representative':
            result = self._run_definition(responsible_object, params=params)
        elif self.responsible_type == 'representative':
            responsible_object_next = self.get_next_responsible(responsible_object)
            result = self.get_user_representative(responsible_object_next)

        return self.to_users(result) or self.env['res.users'].browse()

    def _run_definition(self, responsible_object, params=None, raise_exception=False, ):
        if not isinstance(responsible_object, models.Model):
            if raise_exception:
                raise ValueError("Invalid Responsible Object")
            return False
        rec = self.ensure_one()
        if not rec:
            if raise_exception:
                raise ValueError()
        if rec.responsible_select == 'field':
            return responsible_object and getattr(responsible_object, rec.responsible_field)
        if rec.responsible_select == 'function':
            try:
                return safe_call_method(responsible_object, rec.responsible_function)
            except:
                if raise_exception:
                    _logger.error("Function error , %s , %s ", rec, responsible_object)
                    raise
                _logger.exception("Error")
                return False
        if rec.responsible_select == 'code':
            try:
                localdict = {
                    'result': False,
                    'responsible_object': responsible_object,
                    'approval_responsible': rec,
                    'params': params,
                }
                safe_eval(rec.responsible_code, localdict, mode="exec", nocopy=True)
                return "result" in localdict and localdict["result"] or False
            except:
                if raise_exception:
                    _logger.error("Code error , %s , %s ", rec, responsible_object)
                    raise
                _logger.exception("Error")
                return False
        return False

    def prepare_list_approval_task_line(self, responsible_object, params=None, raise_exception=False, ):
        approval_task_line = []
        responsible_rule = self.ensure_one()
        if not responsible_object or not isinstance(responsible_object, models.Model):
            _logger.error("responsible_object error , %s , %s", responsible_rule, responsible_object)

            if raise_exception:
                raise ValueError("Invalid responsible_object Object")
            return approval_task_line

        if responsible_rule.responsible_select == 'standard':
            if self.responsible_type == 'hierarchy':
                responsible_object_next = responsible_object
                while (isinstance(responsible_object_next, models.Model)):
                    data = responsible_rule.prepare_dict_approval_task_line(responsible_object_next)
                    if data:
                        approval_task_line.append(data)
        if responsible_rule.responsible_select == 'function':
            try:
                return safe_call_method(responsible_object, responsible_rule.responsible_function)
            except:
                if raise_exception:
                    _logger.error("Function error , %s , %s ", responsible_rule, responsible_object)
                    raise
                _logger.exception("Error")
                return False
        if responsible_rule.responsible_select == 'code':
            try:
                localdict = {
                    'result': [],
                    'responsible_object': responsible_object,
                    'responsible_rule': responsible_rule,
                    'params': params,
                }
                safe_eval(responsible_rule.responsibler_code, localdict, mode="exec", nocopy=True)
                return "result" in localdict and localdict["result"] or []
            except:
                if raise_exception:
                    _logger.error("Code error , %s , %s ", responsible_rule, responsible_object)
                    raise
                _logger.exception("Error")
                return []
        return []

    def prepare_dict_approval_task_line(self, responsible_object, **kwargs):
        responsible_rule = self.ensure_one()
        if isinstance(responsible_object, models.Model):
            prepare_dict = {
                'responsible_model': responsible_object._name,
                'responsible_res_id': responsible_object.id,
                'responsible_rule_id': responsible_rule.id,
            }
            user = responsible_rule.get_user_representative(responsible_object)
            if user:
                prepare_dict['responsible_user_id'] = int(user)
            return prepare_dict
        return {}
