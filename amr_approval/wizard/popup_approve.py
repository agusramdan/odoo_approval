
from odoo import fields, models
from odoo.exceptions import UserError


class PopupApproveMessageWizard(models.TransientModel):
    _name = "popup.approve.message.wizard"
    _description = "Popup Approve Message"

    name = fields.Text(string="Note")

    def get_note_approve(self):
        return self.name and "Note Approve => %s" % self.name

    def get_note_chatter(self):
        return self.get_note_approve()

    def button_approve(self):
        context = self.env.context
        active_model = context.get('active_model')
        active_id = context.get('active_id')
        obj = self.env[active_model].browse(active_id)
        if active_model == 'approval.instance':
            approval_instance = obj
        else:
            approval_instance = (
                    getattr(obj, 'approval_instance_id', None) or
                    self.env['approval.instance'].get_instance_for_transaction(active_model, active_id)
            )

        if not approval_instance:
            raise UserError(
                "Model %s required inherit approval.instance.able.mixin and configure approval.template. " % active_model
            )

        return approval_instance.with_context(
            dict(context, default_notes=self.name, __approve_reason=self.name)
        ).do_approve(
            reason=self.name,
            notes_chatter=self.get_note_chatter(),
            popup_approve=self
        )
