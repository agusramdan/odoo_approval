
from odoo import models, fields
from odoo.exceptions import ValidationError


class CreateUserWizard(models.TransientModel):
    _name = 'create.user.wizard'
    _description = 'Create User Wizard'

    name = fields.Char(required=True)
    login = fields.Char(required=True)
    email = fields.Char()

    template_id = fields.Many2one('res.users', required=True)

    def action_create(self):

        self.ensure_one()
        if self.env['res.users'].search([('login', '=', self.login)]):
            raise ValidationError("Login already exists")
        template = self.template_id

        user = self.env['res.users'].create({
            'name': self.name,
            'login': self.login,
            'email': self.email,
            'share': template.share,
            'groups_id': [(4, g.id) for g in template.groups_id],
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'res.users',
            'res_id': user.id,
            'view_mode': 'form',
            'target': 'current',
        }
