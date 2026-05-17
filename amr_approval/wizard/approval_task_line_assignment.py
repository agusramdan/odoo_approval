from odoo import fields, models, api
from odoo.exceptions import ValidationError


class ApprovalTaskLineAssignmentWizard(models.TransientModel):
    _name = 'approval.task.line.assignment.wizard'

    task_line_id = fields.Integer()
    task_line_model = fields.Char()

    from_user_ids = fields.Many2many('res.users')
    new_user_id = fields.Many2one('res.users', required=True)

    reason = fields.Text()

    display_name = fields.Char(
        compute="_compute_display_name",
        string="Record"
    )

    def _compute_display_name(self):
        for rec in self:
            record = self.env[rec.task_line_model].browse(rec.task_line_id)
            rec.display_name = record.display_name if record else False

    @api.constrains('new_user_id')
    def _check_same_user(self):
        for rec in self:
            if rec.new_user_id in rec.from_user_ids:
                raise ValidationError("New responsible user must be different.")

    def action_confirm(self):
        self.ensure_one()

        record = self.env[self.task_line_model].browse(self.task_line_id)

        record.do_assignment(
            new_user_id=self.new_user_id,
            reason=self.reason
        )

        return {'type': 'ir.actions.act_window_close'}
