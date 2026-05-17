# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
import logging

_logger = logging.getLogger(__name__)


class NotificationLog(models.Model):
    _name = "notification.log"
    _inherit = 'approval.transaction.able.mixin'
    _description = "Notification Template"
    _order = 'id desc'

    user_id = fields.Many2one('res.users', default=lambda self: self.env.user)
    notification_template_id = fields.Many2one('notification.template')
    receiver_id = fields.Many2one('res.users')
    payload = fields.Text()
    mail_id = fields.Integer()
    mail_model = fields.Char()
    chat_id = fields.Integer()
    chat_model = fields.Char()
    res_id = fields.Integer()

    def send(self):
        result = {}
        result = self.notification_template_id.with_user(self.user_id).send_notification_to_user(
            self.receiver_id, self.res_id, result,
            transaction_id=self.transaction_id,
            transaction_model_name=self.transaction_model_name
        )
        if result:
            self.write(result)

    def _show_message(self, model, res_id):

        if model and res_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': model,
                'view_mode': 'form',
                'res_id': res_id,
            }

    def action_show_mail(self):
        self.ensure_one()
        self._show_message(self, self.mail_model and self.mail_id)

    def action_show_chat(self):
        self.ensure_one()
        self._show_message(self, self.chat_message_model and self.chat_message_id)
