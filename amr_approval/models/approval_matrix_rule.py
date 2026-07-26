# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models

from ..tools.utils import safe_call_method
from odoo.tools.safe_eval import safe_eval, test_python_expr

_logger = logging.getLogger(__name__)

DEFAULT_CODE = """
# Available variables:
#  - transaction_object 
#----------------------
result = transaction_object.id>0
"""

DEFAULT_CUSTOM_CODE = """
# Available variables:
#  - transaction_object 
#  - responsible_object 
#----------------------
result = []

result.append()
"""


class ApprovalMatrixRule(models.Model):
    _name = "approval.matrix.rule"
    _inherit = ['rule.condition.mixin', 'approval.matrix.rule.mixin', 'mail.thread', 'mail.activity.mixin']
    _description = "Approval Matrix Rule"
    _order = "priority"

    active = fields.Boolean("Active", default=True)
    priority = fields.Integer(default=10)
    name = fields.Char("Name", required=True)
    # limit_amount = fields.Integer()
    approval_matrix_rule_line = fields.One2many(
        'approval.matrix.rule.line', 'approval_matrix_rule_id', copy=True
    )
    requester_group_ids = fields.Many2many('res.groups', string="Requester Group")
    note = fields.Text(string="Description")

    # setup when configuration
    def get_approval_matrix_rule(self, **kwargs):
        approval_matrix_rules = self
        if not approval_matrix_rules:
            approval_matrix_rules = self.search([])
        for rule in approval_matrix_rules:
            if rule.is_satisfy_condition(kwargs):
                return rule
        return self.browse()

    def get_approval_task_line(self, **kwargs):
        return self.prepare_list_approval_task_line(**kwargs)

    def prepare_list_approval_task_line(self, **kwargs):
        if not self:
            return []

        self.ensure_one()
        prepare_list = []
        for line in self.approval_matrix_rule_line:
            line.is_satisfy_condition(kwargs) and prepare_list.extend(line.prepare_list_approval_task_line(**kwargs))
        return prepare_list


class ApprovalMatrixRuleLine(models.Model):
    _name = "approval.matrix.rule.line"
    _inherit = ['rule.condition.mixin', 'approval.responsible.line.mixin']
    _description = """
    Mixin : Approval Task Model
    """
    approval_matrix_rule_id = fields.Many2one(
        'approval.matrix.rule',
        "Approval Matrix Rule",
        ondelete='cascade'
    )
    sequence = fields.Integer("Sequence", default=10)
    name = fields.Char("Description", help="Signature Title")
    type_approval = fields.Selection([
        ('user', "User"),
        ('group', "Group"),
        ('model', "Model Responsible"),
    ], default='group')
    user_ids = fields.Many2many('res.users', string="Approval Users")
    group_ids = fields.Many2many('res.groups', string="Approval Group")

    reject_to_method = fields.Selection([
        ('to_requestor', "To Requestor"),
        ('to_previous', "To Previous"),
        ('to_task_line', "To Task Line"),
    ], default='to_previous', readonly=True)
    reject_to_line_id = fields.Many2one(
        'approval.matrix.rule.line',
        "Reject To Line",
        ondelete='set null'
    )
    model_id = fields.Many2one("ir.model", related='responsible_rule_id.model_id')
    responsible_mode = fields.Selection([
        ('select', 'Select'),
        ('field', 'Field'),
        ('function', 'Function'),
        ('code', 'Code'),
    ])
    responsible_field = fields.Char(
        help="Filed document boolean for need approval."
    )
    responsible_function = fields.Char(
        help="Code document boolean for need approval."
    )
    responsible_code = fields.Text(
        default=DEFAULT_CODE,
        help="Code document boolean for need approval."
    )

    get_responsible_mode = fields.Selection([
        ('field', 'Field'),
        ('function', 'Function'),
        ('code', 'Code'),
    ])
    get_responsible_field = fields.Char(
        help="Filed document boolean for need approval."
    )
    get_responsible_function = fields.Char(
        help="Code document boolean for need approval."
    )
    get_responsible_code = fields.Text(
        default=DEFAULT_CODE,
        help="Code document boolean for need approval."
    )

    responsible_strategy = fields.Selection([
        ('hierarchy', 'Hierarchy'),
        ('hierarchy_next', 'Hierarchy Next'),
        ('representative', 'Representative'),
        ('all_member', 'All Member'),
        ('custom', 'Custom Code'),
    ], default='hierarchy')

    responsible_custom = fields.Text(
        default=DEFAULT_CUSTOM_CODE,
        help="Code ."
    )

    @api.model_create_multi
    @api.returns('self', lambda value: value.id)
    def create(self, vals_list):
        for vals in vals_list:
            if 'reject_to_line_id' in vals and vals['reject_to_line_id']:
                vals['reject_to_method'] = 'to_task_line'

        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if 'reject_to_line_id' in vals and vals['reject_to_line_id']:
            vals['reject_to_method'] = 'to_task_line'

        return res

    def get_responsible_object(self, raise_exception=True, **kwargs):
        transaction_object = kwargs.get('transaction_object')
        responsible_object = None
        line = self.ensure_one()
        if line.responsible_mode == 'select':
            responsible_object = self.env[line.responsible_model].browse(line.responsible_id)
        elif line.responsible_mode == 'field':
            responsible_object = getattr(
                transaction_object,
                line.get_responsible_field,
                None
            )
        elif line.responsible_mode == 'function':
            try:
                responsible_object = safe_call_method(
                    transaction_object,
                    line.responsible_function, kwargs=kwargs
                )
            except:
                if raise_exception:
                    _logger.error("Function error , %s , %s ", line, transaction_object)
                    raise
                _logger.exception("Error")
                responsible_object = None

        elif line.responsible_mode == 'code':
            try:
                localdict = {
                    'result': [],
                    'transaction_object': transaction_object,
                    'params': kwargs,
                }
                safe_eval(line.responsible_code, localdict, mode="exec", nocopy=True)
                responsible_object = "result" in localdict and localdict["result"] or []
            except:
                if raise_exception:
                    _logger.error("Code error , %s , %s ", line, transaction_object)
                    raise
                _logger.exception("Error")
                responsible_object = None
        return responsible_object

    def get_custom_responsible_strategy_prepare_list_approval_task_line(
            self, responsible_object, params=None, raise_exception=True,
    ):
        approval_task_line = []
        try:
            localdict = {
                'result': [],
                'responsible_object': responsible_object,
                'responsible_rule': self.responsible_rule_id,
                'params': params or {},
            }
            safe_eval(self.responsible_custom, localdict, mode="exec", nocopy=True)
            approval_task_line = "result" in localdict and localdict["result"] or []
        except:
            if raise_exception:
                _logger.error("Code error , %s , %s ", self.responsible_rule_id, responsible_object)
                raise
            _logger.exception("Error")
        return approval_task_line

    def prepare_list_approval_task_line(self, **kwargs):
        self.ensure_one()
        prepare_list = []
        if self.type_approval in ['group', 'user']:
            prepare_list = [self.prepare_dict_approval_task_line(**kwargs)]
        elif self.type_approval == 'model':
            prepare_dict = self.prepare_dict_approval_task_line(**kwargs)
            responsible_object = self.get_responsible_object(**kwargs)
            if self.responsible_strategy in ['hierarchy', 'hierarchy_next']:
                kw = dict(kwargs)
                kw.pop('responsible_object', None)
                kw.pop('get_action', None)
                kw.pop('include', None)
                prepare_list = self.responsible_rule_id.prepare_list_approval_task_line(
                    responsible_object=responsible_object,
                    get_action='hierarchy_list',
                    include=self.responsible_strategy == 'hierarchy',
                    **kw
                )
            elif self.responsible_strategy == 'representative':
                kw = dict(kwargs)
                kw.pop('responsible_object', None)
                kw.pop('get_action', None)
                prepare_list = self.responsible_rule_id.prepare_list_approval_task_line(
                    responsible_object=responsible_object,
                    get_action='representative',
                    **kw
                )
            elif self.responsible_strategy == 'all_member':
                members = self.responsible_rule_id.get_members(responsible_object, params=kwargs)
                kw = dict(kwargs)
                kw.pop('responsible_object', None)
                kw.pop('members', None)
                prepare_list = [self.responsible_rule_id.prepare_dict_approval_task_line(
                    responsible_object=responsible_object, members=members, **kw
                )]
            elif self.responsible_strategy == 'custom':
                prepare_list = self.get_custom_responsible_strategy_prepare_list_approval_task_line(
                    responsible_object, params=kwargs
                )
                # ensure return list
                if prepare_list and not isinstance(prepare_list, (list, tuple)):
                    prepare_list = [prepare_list]
            if prepare_list and prepare_dict:
                return [{**prepare_dict, **d} for d in prepare_list if d]
        return prepare_list

    def prepare_dict_approval_task_line(self, **kwargs):
        p_dict = {
            'sign_title': self.name,
            'matrix_rule_line_id': self.id
        }
        if not self.env.context.get('__approval_matrix_rule_line') and self.type_approval == 'user':
            p_dict.update(
                self.user_ids.with_context(
                    __approval_matrix_rule_line=self.id
                ).prepare_dict_approval_task_line(**kwargs)
            )
        if not self.env.context.get('__approval_matrix_rule_line') and self.type_approval == 'group':
            p_dict.update(
                self.group_ids.with_context(
                    __approval_matrix_rule_line=self.id
                ).prepare_dict_approval_task_line(**kwargs)
            )

        return p_dict

    def action_open_line(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
