
from odoo import fields, models
from datetime import datetime


class PopupRejectMessageWizard(models.TransientModel):
    _name = "popup.reject.message.wizard"
    _description = "Popup Reject Message"

    name = fields.Text(string="Note", required=True)

    def get_note_reject(self):
        return "Note Reject => %s" % self.name

    def button_reject(self):
        context = self.env.context
        obj = self.env[context.get('active_model')].browse(context.get('active_id'))
        obj.with_context(dict(context, default_notes=self.name,__reject_reason=self.name)).reject_from_popup_reject(
            reason=self.name,
            popup_reject=self
        )
