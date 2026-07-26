# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.tools.safe_eval import safe_eval, test_python_expr
from ..tools.utils import have_method, safe_call_method

_logger = logging.getLogger(__name__)

DEFAULT_CODE = """
# Available variables:
#  - responsible_object 
#  - approval_responsible
#  - params
#----------------------
result = responsible_object.acting_manager_id or responsible_object.manager_id
"""


class ApprovalResponsibleLineMixin(models.AbstractModel):
    _name = 'approval.responsible.line.mixin'

    assign_responsible_rule = fields.Selection([
        ('legacy', 'Legacy'),
        ('have_one_user', 'Have One User'),
        ('pickup', 'Pickup Responsible'),
    ], 'Responsible', default='legacy')
    responsible_rule_id = fields.Many2one('approval.responsible', 'Responsible Rule')
    responsible_model = fields.Char(
        'Responsible', readonly=True, related='responsible_rule_id.model',
        help="The database object this attachment will be attached to."
    )
    responsible_id = fields.Many2oneReference(
        'Responsible', model_field='responsible_model',
        help="The record id this is attached to."
    )
    responsible_ref = fields.Reference(
        selection='_selection_models_responsible',
        compute='_compute_responsible_ref',
        inverse='_inverse_responsible_ref',
        string='Responsible',
        store=False,
    )
    responsible_user_id = fields.Many2one(
        'res.users', 'Responsible User',
        help="The record id this is attached to."
    )

    @api.depends('responsible_model', 'responsible_id')
    def _compute_responsible_ref(self):
        for rec in self:
            if rec.responsible_model and rec.responsible_id:
                rec.responsible_ref = "%s,%s" % (
                    rec.responsible_model,
                    rec.responsible_id,
                )
            elif rec.responsible_model:
                rec.responsible_ref = "%s,0" % rec.responsible_model
            else:
                rec.responsible_ref = False

    @api.model
    def _selection_models_responsible(self):
        responsible_list = self.env['approval.responsible'].search([])
        return [(r.model, r.display_name) for r in responsible_list]

    def _inverse_responsible_ref(self):
        for rec in self:
            if rec.responsible_ref:
                rec.responsible_rule_id = self.responsible_rule_id.search(
                    [('model_id.model', '=', rec.responsible_ref._name)], limit=1
                )
                # rec.responsible_model = rec.responsible_ref._name
                rec.responsible_id = rec.responsible_ref.id
            else:
                rec.responsible_id = False

    def get_responsible_object(self):
        return self.env[self.responsible_rule_id.model].browse(self.responsible_id)

    def get_responsible_members_user(self):
        if self and self.responsible_rule_id.members:
            responsible_object = self.get_responsible_object()
            return self.responsible_rule_id.get_members(responsible_object) or self.env['res.users'].browse()
        return self.env['res.users'].browse()

    def do_assignment(self, new_user_id, reason=None):
        if have_method(self, 'get_users'):
            old_users = self.get_users()
        else:
            old_users = self.responsible_user_id
        self.env['approval.task.assignment.history'].sudo().create([{
            'task_line_id': self.id,
            'task_line_model': self._name,
            'from_user_ids': [(6, 0, old_users.ids)] if old_users else [],
            'new_user_id': int(new_user_id),
            'reason': reason,
            'reassigned_by': self.env.uid
        }])
        self.write({
            'responsible_user_id': int(new_user_id),
        })
        if have_method(self, "register_to_approval_task"):
            self.register_to_approval_task()

    def action_assignment(self):
        self.ensure_one()
        if have_method(self, 'get_users'):
            old_users = self.get_users()
        else:
            old_users = self.responsible_user_id
        # call wizard to select new user and reason
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reassign Approval Task',
            'res_model': 'approval.task.line.assignment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_task_line_id': self.id,
                'default_task_line_model': self._name,
                'default_from_user_ids': old_users.ids if old_users else [],
                'default_responsible_rule_id': self.responsible_rule_id.id,
                'default_responsible_id': self.responsible_id,
            }
        }


class ApprovalResponsible(models.Model):
    _name = 'approval.responsible'
    _description = "responsible user for approval"
    _rec_name = 'model_id'
    _sql_constraints = [
        ('model_id_unique', 'unique(model_id)', 'Model must be uniq!')
    ]
    active = fields.Boolean(default=True)
    name = fields.Char()
    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade', )
    model = fields.Char(related='model_id.model')

    hierarchy = fields.Boolean(
        help="When True have hierarchy model"
    )
    hierarchy_select = fields.Selection([
        ('field', 'Field'),
        ('function', 'Function'),
        ('code', 'Code'),
    ], default='field', required=True)
    hierarchy_field = fields.Char(
        help="Filed document boolean for need approval."
    )
    hierarchy_function = fields.Char(
        help="Function for need approval."
    )
    hierarchy_code = fields.Text(
        default=DEFAULT_CODE,
        help="Code document boolean for need approval."
    )
    # represenative
    representative = fields.Boolean(
        help="Representative berarti bertindak atas nama (delegate/acting)."
    )
    representative_select = fields.Selection([
        ('field', 'Field'),
        ('function', 'Function'),
        ('code', 'Code'),
    ], default='field', required=True)
    representative_field = fields.Char(
        help="Filed document boolean for need approval."
    )
    representative_function = fields.Char(
        help="Function for need approval."
    )
    representative_code = fields.Text(
        default=DEFAULT_CODE,
        help="Code document boolean for need approval."
    )

    # Members
    members = fields.Boolean(
        help="When True have membes model"
    )
    members_select = fields.Selection([
        ('field', 'Field'),
        ('function', 'Function'),
        ('code', 'Code'),
    ], default='field', required=True)
    members_field = fields.Char(
        help="Filed document boolean for need approval."
    )
    members_function = fields.Char(
        help="Function for need approval."
    )
    members_code = fields.Text(
        default=DEFAULT_CODE,
        help="Code document boolean for need approval."
    )

    def get_data_responsible_object(self, data_type, responsible_object, params=None, raise_exception=True):
        data_select = getattr(self, f"{data_type}_select", "")
        if not data_select:
            return None

        data_target = getattr(self, f"{data_type}_{data_select}", "")
        if not data_target:
            return None

        if data_select == 'field':
            return responsible_object and getattr(responsible_object, data_target)
        if data_select == 'function':
            try:
                return safe_call_method(responsible_object, data_target)
            except:
                if raise_exception:
                    _logger.error("Function error , %s , %s ", self, responsible_object)
                    raise
                _logger.exception("Error")
                return False
        if data_select == 'code':
            try:
                localdict = {
                    'result': False,
                    'responsible_object': responsible_object,
                    'approval_responsible': self,
                    'params': params,
                }
                safe_eval(data_target, localdict, mode="exec", nocopy=True)
                return "result" in localdict and localdict["result"] or False
            except:
                if raise_exception:
                    _logger.error("Code error , %s , %s ", self, responsible_object)
                    raise
                _logger.exception("Error")
                return False
        return False

    def get_hierarchy_next(self, responsible_object, params=None, raise_exception=True):
        return self.get_data_responsible_object(
            'hierarchy', responsible_object, params=params, raise_exception=raise_exception
        )

    def get_hierarchy_list(self, responsible_object, params=None, raise_exception=True, include=False):
        # responsible_object inclued in list include
        result = []
        while responsible_object:
            if include:
                result.append(responsible_object)
            else:
                include = True
            responsible_object = self.get_hierarchy_next(
                responsible_object, params=params, raise_exception=raise_exception
            )

        return result

    def get_representative(self, responsible_object, params=None, raise_exception=True):
        representative = self.get_data_responsible_object(
            'representative', responsible_object, params=params, raise_exception=raise_exception
        )
        return self.to_users(representative)

    def get_members(self, responsible_object, params=None, raise_exception=True):
        if self.members:
            members = self.get_data_responsible_object(
                'members', responsible_object, params=params, raise_exception=raise_exception
            )
            return members
        return self.env['res.users'].browse()

    @api.model
    def is_auto_representative(self):
        return self.model_auto_representative(self.model)

    @api.model
    def model_auto_representative(self, model):
        return model in ['hr.department', 'hr.employee', 'resource.resource']

    @api.model
    def to_users(self, responsible_object):
        if responsible_object and isinstance(responsible_object, models.Model):
            if responsible_object._name == 'hr.department':
                responsible_object = responsible_object.manager_id
            if responsible_object._name == 'hr.employee':
                responsible_object = responsible_object.user_id
            if responsible_object._name == 'resource.resource':
                responsible_object = getattr(responsible_object, 'user_id', None) or self.env['res.users'].browse()
            if responsible_object._name == 'res.groups':
                responsible_object = responsible_object.users
            if responsible_object._name == 'res.users':
                return responsible_object

        return self.env['res.users'].browse()

    def prepare_list_approval_task_line(
            self, responsible_object=None, get_action='representative', **kwargs):
        if get_action == 'representative':
            return [self.prepare_dict_approval_task_line(responsible_object=responsible_object, **kwargs)]
        if get_action == 'hierarchy_list':
            list_h = self.get_hierarchy_list(responsible_object, include=kwargs.get('include'))
            return [self.prepare_dict_approval_task_line(r, **kwargs) for r in list_h]
        if get_action == 'hierarchy_next':
            r = self.get_hierarchy_next(responsible_object)
            return [self.prepare_dict_approval_task_line(r, **kwargs)]

        return []

    def prepare_dict_approval_task_line(self, responsible_object=None, members=None, **kwargs):
        responsible_rule = self.ensure_one()
        if isinstance(responsible_object, models.Model):
            prepare_dict = {
                'responsible_model': responsible_object._name,
                'responsible_id': responsible_object.id,
                'responsible_rule_id': responsible_rule.id,
            }
            if members:
                if isinstance(members, models.Model):
                    if members._name == 'res.users':
                        user = members
                    else:
                        user = self.to_users(members)
                else:
                    return prepare_dict
            elif responsible_object._name == responsible_rule.model:
                user = responsible_rule.get_representative(responsible_object)
            elif responsible_rule.is_auto_representative():
                user = self.to_users(responsible_object)
            elif responsible_object._name == 'res.users':
                user = responsible_object
            else:
                user = None
            if user:
                prepare_dict['user_ids'] = user.ids
                prepare_dict['type_approval'] = 'multi_user'
                if len(user) == 1:
                    prepare_dict['type_approval'] = 'user'
                    prepare_dict['responsible_user_id'] = user.id
                    prepare_dict['user_id'] = user.id
                    prepare_dict['assign_responsible_rule'] = 'have_one_user'
                else:
                    prepare_dict['user_id'] = user.ids[0]

            return prepare_dict
        return {}
