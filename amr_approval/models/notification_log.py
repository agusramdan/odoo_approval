# -*- coding: utf-8 -*-
import json

import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class NotificationLog(models.Model):
    _name = "notification.log"
    _inherit = 'approval.transaction.able.mixin'
    _description = "Notification Log"
    _order = 'id desc'

    name = fields.Char()
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user, ondelete="set null", )
    notification_template_id = fields.Many2one('notification.template', ondelete="set null", )
    receiver_id = fields.Many2one('res.users', ondelete="set null", )
    payload = fields.Text()
    mail_id = fields.Integer()
    mail_model = fields.Char()
    chat_id = fields.Integer()
    chat_model = fields.Char()
    mobile_id = fields.Integer()
    mobile_model = fields.Char()
    res_id = fields.Integer()

    def send(self):
        result = {}
        result = self.notification_template_id.with_user(self.user_id).send_notification_to_user(
            self.receiver_id, self.res_id, notif_log=result,
            payload=None,
            transaction_id=self.transaction_id,
            transaction_model_name=self.transaction_model_name
        )
        if result:
            self.write(result)

    def send_payload(self):
        payload = json.loads(self.payload)
        result = {}
        result = self.notification_template_id.with_user(self.user_id).send_notification_to_user(
            self.receiver_id, self.res_id, notif_log=result,
            payload=payload,
            transaction_id=self.transaction_id,
            transaction_model_name=self.transaction_model_name
        )
        if result:
            if payload.get('title'):
                result['name'] = payload.get('title')
            self.write(result)

    def _show_message(self, model, res_id):

        if model and res_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': model,
                'view_mode': 'form',
                'res_id': res_id,
            }
        else:
            raise UserError("Error Shoe %s , %s " % (model, res_id))

    def send_mobile(self):
        self.ensure_one()
        payload = json.loads(self.payload)
        result = {}
        result = self.notification_template_id.with_user(
            self.user_id
        ).send_notification_mobile(
            self.receiver_id, payload, result, self.res_id,
            transaction_id=self.transaction_id,
            transaction_model_name=self.transaction_model_name
        )
        if result:
            self.write(result)

    def action_show_mail(self):
        self.ensure_one()
        return self._show_message(self.mail_model, self.mail_id)

    def action_show_chat(self):
        self.ensure_one()
        return self._show_message(self.chat_model, self.chat_id)

    def action_show_mobile(self):
        self.ensure_one()
        return self._show_message(self.mobile_model, self.mobile_id)
