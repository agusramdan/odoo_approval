# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval, test_python_expr

from ..tools.utils import safe_call_method

_logger = logging.getLogger(__name__)


class ChatTemplate(models.Model):
    _name = "chat.template"
    _description = "Chat/Mobile/WA Template"
    """
    Chat using firebase model message for send to api.
    """

    active = fields.Boolean(default=True)
    name = fields.Char("Notification")
    model_id = fields.Many2one('ir.model')
    model = fields.Char("Model", related="model_id.model")
    DEFAULT_PYTHON_CODE = """# Available variables:
            #  - env: Odoo Environment on which the action is triggered
            #  - notification
            #  - data : data part notification firebase
            # To return an response, assign: response = {...}

            \n\n\n\n
            """
    title = fields.Char()
    body = fields.Char()
    image = fields.Char()
    body_html = fields.Text()
    code = fields.Text(
        string='Python Code',
        default=DEFAULT_PYTHON_CODE,
        help="Write Python code that the action will execute. Some variables are "
             "available for use; help about python expression is given in the help tab."
    )

    def get_application_name(self):
        return self.env['ir.config_parameter'].get_param('amr.application_name')

    def send_notification_to_users(self, users, res_id, **kwargs):
        for notification_to_user in users:
            self.with_context(notification_to_user=notification_to_user).send(notification_to_user, res_id)

    def send_notification_to_user(self, notification_to_user, res_id, notif_log=None, **kwargs):
        Template = self.env['mail.template']
        template = self.ensure_one()
        fields = ['title', 'body', 'image', 'body_html']
        notification = {}
        for field in fields:
            Template = Template.with_context(safe=field in {'title'})
            notification[field] = Template._render_template(getattr(template, field), template.model, res_id)

        data = {
            'notification_to_user': notification_to_user.partner_id.email,
        }
        body = notification.get('body')
        body_html = notification.pop('body_html')
        if body_html:
            data['body_html'] = body_html
        approval_task_line = kwargs.get('approval_task_line')
        if approval_task_line:
            data.update(
                source_approval_model=approval_task_line._name,
                source_approval_res_id=approval_task_line.id
            )
        eval_context = self._get_eval_context()
        transaction_object = self.env[self.model].sudo().browse(res_id)
        eval_context['object'] = eval_context['record'] = transaction_object
        eval_context['notification'] = notification
        eval_context['data'] = data
        eval_context = self._run_action_code_multi(eval_context)
        data = eval_context.get('data')
        if 'url' not in data and not data.get('url'):
            data['source_url'] = safe_call_method(transaction_object, 'get_internal_url') or None
        # payload is firebase format notification
        payload = {
            'notification': eval_context.get('notification'),
            'data': data
        }

        self.send_notification(notification_to_user, payload, notif_log=notif_log, **kwargs)

    @api.model
    def send_notification(self, notification_to_user, payload, notif_log=None, **kwargs):
        # payload is firebase format notification
        chat_message = notification_to_user.send_odoobot_message(
            payload.get('data', {}).get('body_html') or payload.get('notification', {}).get('body')
        )
        if chat_message and notif_log is not None:
            notif_log['chat_message_id'] = chat_message.id
            notif_log['chat_message_model'] = chat_message._model

    @api.model
    def _get_eval_context(self):
        """ evaluation context to pass to safe_eval """

        return {
            'env': self.env,
            'uid': self._uid,
            'user': self.env.user,
        }

    @api.constrains('code')
    def _check_python_code(self):
        for action in self.sudo().filtered('code'):
            msg = test_python_expr(expr=action.code.strip(), mode="exec")
            if msg:
                raise ValidationError(msg)

    def _run_action_code_multi(self, eval_context):
        safe_eval(self.code.strip(), eval_context, mode="exec", nocopy=True)  # nocopy allows to return 'action'
        return eval_context
