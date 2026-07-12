# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
import logging

_logger = logging.getLogger(__name__)


class ReminderLog(models.Model):
    _name = "reminder.log"
    _inherit = 'approval.transaction.able.mixin'
    _description = "Reminder Log"
    _order = 'id desc'

    notification_log_id = fields.Many2one("notification.log", ondelete="set null", )
    request_approval_task_date = fields.Datetime('Request Approval Task Date')
    reminder_count = fields.Integer()
    reminder_datetime = fields.Datetime('Reminder Datetime')
    receiver_id = fields.Many2one('res.users', ondelete="set null", )

