# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models

from ..tools.utils import safe_call_method

_logger = logging.getLogger(__name__)


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
    _inherit = ['rule.condition.mixin']
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
        ('group', "Group"),
        ('model', "Model"),
    ], default='group')
    group_ids = fields.Many2many('res.groups', string="Approval Group")
    model_id = fields.Many2one("ir.model", string="Model", ondelete='set null')
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

    def prepare_list_approval_task_line(self, **kwargs):
        self.ensure_one()
        prepare_list = []
        if self.type_approval == 'group':
            prepare_list.append(self)
        elif self.type_approval == 'model':
            line = self.env[self.model_id.model]
            line_list = safe_call_method(
                line.with_context(
                    approval_matrix_rule_line=self,
                    approval_matrix_rule_line_id=self.id
                ),
                'prepare_line_approval_task_line',
                kwargs=kwargs
            )
            if line_list:
                prepare_list.extend(line_list)
            else:
                _logger.warning(
                    "Method prepare_line_approval_task_line return empty for model %s", self.model_id.model
                )
                prepare_list.append(line)
        # elif self.type_approval == 'matrix':
        #     prepare_list.extend(self.matrix_id.prepare_list_approval_task_line(**kwargs))
        return prepare_list

    def prepare_dict_approval_task_line(self, **kwargs):
        p_dict = {
            'sign_title': self.name,
            'matrix_rule_line_id': self.id
        }

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
