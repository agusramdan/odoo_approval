# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ServerActions(models.Model):
    _inherit = "ir.actions.server"

    state = fields.Selection(
        selection_add=[("notif_approval", "Notification Approval"), ("chatter", "Chatter Message")],
    )
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
             "Reminder Approval : Notification Remainder Request Approval to Approver.",
        compute="_compute_notification_type",
        store=True,
    )
    notification_template_id = fields.Many2one(
        "notification.template",
        "Notification Template",
        domain="[('model_id', '=', model_id)]",
    )
    chatter_type = fields.Selection(
        [
            ('approval', 'Request Approval'),
            ('cancel', 'Cancel'),
            ('reset', 'Reset To Draft'),
            ('reject', 'Rejection'),
            ('approve', 'Approve'),
        ],
        compute="_compute_chatter_type",
        store=True,
    )
    chatter_template_id = fields.Many2one(
        "chatter.template",
        "Chatter Template",
        domain="[('model_id', '=', model_id)]",
    )

    @api.depends('notification_template_id', 'notification_template_id.notification_type')
    def _compute_notification_type(self):
        for action in self:
            if action.state == 'notif_approval' and action.notification_template_id:
                action.notification_type = action.notification_template_id.notification_type
            else:
                action.notification_type = None

    @api.depends('chatter_template_id', 'chatter_template_id.chatter_type')
    def _compute_chatter_type(self):
        for action in self:
            if action.state == 'chatter' and action.chatter_template_id:
                action.chatter_type = action.chatter_template_id.chatter_type
            else:
                action.chatter_type = None

    @api.constrains('state', 'model_id')
    def _check_notif_approval_capability(self):
        for action in self:
            if action.state == 'notif_approval':
                if not action.notification_template_id:
                    raise ValidationError(_("Call notif_approval mandatory."))

                if action.notification_template_id.model_id != action.model_id:
                    raise ValidationError(_("Call notif_approval model miss match."))

    @api.model
    def run_action_notif_approval(self, action, eval_context=None):
        # TDE CLEANME: when going to new api with server action, remove action
        if not action.notification_template_id or self._is_recompute(action):
            return False
        notification_to_users = eval_context.get('notification_to_users')
        if not notification_to_users:
            notification_to_users = eval_context.get('env').context.get('notification_to_users')
        if not notification_to_users:
            notification_to_users = eval_context.get('notification_to_user')
        if not notification_to_users:
            notification_to_users = eval_context.get('env').context.get('notification_to_user')
        eval_context['notification_to_users'] = notification_to_users
        eval_context['rec_id'] = eval_context['active_id'] = eval_context.get('active_id') or eval_context.get('env').context.get('active_id')
        return action.notification_template_id.run_action_notif_approval(eval_context=eval_context)

    @api.model
    def run_action_chatter(self, action, eval_context=None):
        # TDE CLEANME: when going to new api with server action, remove action
        if not action.chatter_template_id or self._is_recompute(action):
            return False

        return action.chatter_template_id.run_action_chatter(eval_context=eval_context)
