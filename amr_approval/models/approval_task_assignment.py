# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models
from ..tools.utils import have_method

_logger = logging.getLogger(__name__)


# deprecated move to approval.task.line.assignment.mixin change to approval.responsible.line.mixin
class ApprovalTaskLineAssignmentMixin(models.AbstractModel):
    _name = "approval.task.line.assignment.mixin"
    _description = "Mixin : Approval Task Line Assignment"

    responsible_user_id = fields.Many2one('res.users', 'Responsible User')

    def search_responsible_user(self, user_id):
        return self.search([('responsible_user_id', '=', user_id)])

    def revoke_assignment(self):
        self.write({
            'responsible_user_id': False,
        })

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
            }
        }


class ApprovalTaskAssignmentHistory(models.Model):
    _name = 'approval.task.assignment.history'
    _description = 'Approval Task Assignment History'

    task_line_id = fields.Integer()
    task_line_model = fields.Char()

    from_user_ids = fields.Many2many('res.users')
    new_user_id = fields.Many2one('res.users')

    reason = fields.Text()
    reassigned_by = fields.Many2one(
        'res.users',
        default=lambda self: self.env.user,
    )
    reassigned_at = fields.Datetime(
        default=fields.Datetime.now
    )


class ApprovalMassAssignmentCommand(models.Model):
    _name = 'approval.mass.assignment.command'
    _description = 'Mass Assignment Command'

    name = fields.Char(required=True)

    execution_type = fields.Selection([
        ('immediate', 'Immediate'),
        ('scheduled', 'Scheduled'),
    ], default='immediate')

    scheduled_at = fields.Datetime()

    mode = fields.Selection([('responsible', 'Responsible'), ('user', 'User')])
    responsible_model = fields.Char('Responsible Model')
    responsible_id = fields.Integer('Responsible ID')

    old_user_id = fields.Many2one('res.users')
    new_user_id = fields.Many2one('res.users')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting', 'Waiting Execution'),
        ('done', 'Done'),
        ('failed', 'Failed'),
    ], default='draft')

    executed_at = fields.Datetime()

    @api.model
    def _cron_execute_mass_assignment(self):
        commands = self.search([
            ('execution_type', '=', 'scheduled'),
            ('state', 'in', ['draft', 'waiting']),
            ('scheduled_at', '<=', fields.Datetime.now()),
        ])

        for command in commands:
            command.action_execute()

    def action_execute(self):
        for command in self:

            if command.execution_type == 'scheduled':
                if command.scheduled_at > fields.Datetime.now():
                    command.state = 'waiting'
                    continue

            try:
                if command.mode == 'user':
                    task_lines = self.env['approval.task'].search([('responsible_user_id', '=', command.old_user_id)])
                    for line in task_lines:
                        line.do_assignment(
                            new_user_id=command.new_user_id.id,
                            reason=f"Mass assignment: {command.name}",
                        )

                elif command.mode == 'responsible':
                    task_lines = self.env['approval.task'].search([
                        ('responsible_model', '=', command.responsible_model),
                        ('responsible_id', '=', command.responsible_id)
                    ])

                    for line in task_lines:
                        line.action_responsible_assignment()
                command.state = 'done'
                command.executed_at = fields.Datetime.now()

            except Exception as e:
                command.state = 'failed'
                raise e
