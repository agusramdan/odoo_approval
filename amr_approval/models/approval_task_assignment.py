# -*- coding: utf-8 -*-

from odoo import models, fields, api
from ..tools.utils import have_method
import logging

_logger = logging.getLogger(__name__)


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
        default=lambda self: self.env.user
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
    task_line_model = fields.Char(required=True)
    old_user_id = fields.Many2one('res.users', required=True)
    new_user_id = fields.Many2one('res.users', required=True)

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
            ('scheduled_at', '<=', fields.Datetime.now())
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
                task_lines = self.env[command.task_line_model].search_responsible_user(command.old_user_id)
                for line in task_lines:
                    line.do_assignment(
                        new_user_id=command.new_user_id.id,
                        reason=f"Mass assignment: {command.name}"
                    )

                command.state = 'done'
                command.executed_at = fields.Datetime.now()

            except Exception as e:
                command.state = 'failed'
                raise e
