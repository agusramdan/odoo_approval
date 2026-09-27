# -*- coding: utf-8 -*-

import logging
import traceback

from odoo import api, fields, models
from odoo.exceptions import UserError
from ..tools.utils import have_method, safe_call_method

_logger = logging.getLogger(__name__)


class ApprovalTemplateLineMixin(models.Model):
    _name = 'approval.template.notification'

    # when parent mode specific parent model mandatory
    approval_template_id = fields.Many2one('approval.template')
    model = fields.Char(related='approval_template_id.model')
    approval_task_line_model = fields.Char(related='approval_template_id.approval_task_line_model_id.model')
    action_id = fields.Many2one('ir.actions.server')
    notification_type = fields.Selection(
        [
            ('request_approval', 'Request Approval'),
            ('reminder_approval', 'Reminder Approval'),
            ('cancel', 'Cancel'),
            ('reset', 'Reset To Draft'),
            ('reject', 'Rejection'),
            ('rejection_requester', 'Rejection to Requester'),
            ('rejection_approver', 'Rejection to Approver'),
            ('approve', 'Approve'),
            ('final_approve', 'Final Approve'),
        ],
        help="Approval Notification type"
             "Request Approval : Notification Request Approval to Approver."
             "Reminder Approval : Notification Remainder Request Approval to Approver."
    )

    def send_notification(self, notification_type, notification_to_users, res_id=None, **kwargs):
        notif_template = self.env['notification.template']
        for notif in self:
            if notif.notification_type == notification_type:
                if notif.action_id:
                    active_id = notif_template.ensure_res_id(
                        res_id=res_id, notification_model=notif.action_id.model_name, **kwargs
                    )
                    if not active_id:
                        _logger.warning(
                            "Notification template %s has no active_id for model %s with res_id %s",
                            notif.action_id.name, notif.action_id.model_name, res_id
                        )
                        continue
                    ctx = {
                        'notification_to_users': notification_to_users,
                        **kwargs,
                        'active_id': active_id,
                        'res_id': active_id
                    }
                    notif.action_id.with_context(ctx).run()
