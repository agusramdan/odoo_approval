# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models
from ..tools.utils import safe_call_method
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval, test_python_expr

_logger = logging.getLogger(__name__)

DEFAULT_PYTHON_CODE = """# Available variables:
#  - env: Odoo Environment on which the action is triggered
#  - notification
#  - data : data part notification firebase
# To return an response, assign: response = {...}

\n\n\n\n
"""


class NotificationTemplate(models.Model):
    _name = "notification.template"
    _description = "Notification Template"

    @property
    def send_mobile(self):
        return self.send_firebase or self.send_firebase or self.send_telegram

    active = fields.Boolean(default=True)
    name = fields.Char("Notification")
    model_id = fields.Many2one('ir.model')
    model = fields.Char(related='model_id.model', store=True)

    send_email = fields.Boolean("Send Email", default=False)
    send_chat = fields.Boolean("Send Chat", default=False)
    send_firebase = fields.Boolean("Send Firebase", default=False)
    send_whatsapp = fields.Boolean("Send Whatsapp", default=False)
    send_telegram = fields.Boolean("Send Telegram", default=False)

    template_email = fields.Many2one('mail.template')
    title = fields.Char()
    body = fields.Char()
    body_html = fields.Text()
    body_whatsapp = fields.Text()
    body_telegram = fields.Text()
    image = fields.Char()
    code = fields.Text(
        string='Python Code',
        default=DEFAULT_PYTHON_CODE,
        help="Write Python code that the action will execute. Some variables are "
             "available for use; help about python expression is given in the help tab."
    )

    template_chat = fields.Many2one('chat.template')

    @api.model_create_multi
    @api.returns('self', lambda value: value.id)
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('model_id'):
                vals['model_id'] = self.model_id.search([('model', '=', vals.get('model'))], limit=1).id

        results = super(NotificationTemplate, self).create(vals_list)
        for res in results:
            if res.model_id and res.model_id.model != res.model:
                res.model = res.model_id.model
        return results

    def write(self, vals):
        result = super(NotificationTemplate, self).write(vals)
        if not self.env.context.get('skip_update_model_id'):
            for res in self.with_context(skip_update_model_id=True):
                if res.model_id.model != res.model:
                    if res.model_id:
                        res.write({'model': res.model_id.model})
                    elif res.model:
                        res.write({'model_id': self.model_id.search([('model', '=', res.model)], limit=1).id})
        return result

    def send_notification_to_users(self, users, res_id, **kwargs):
        if not users or not res_id:
            return
        self.ensure_one()
        for notification_to_user in users:
            notif_log = {}
            self.send_notification_to_user(notification_to_user, res_id, notif_log, **kwargs)
            if notif_log:
                notif_log['res_id'] = res_id
                notif_log['receiver_id'] = notification_to_user.id
                notif_log['notification_template_id'] = self.id
                self.env['notification.log'].create(notif_log)

    def send_notification_to_user(self, notification_to_user, res_id, notif_log, **kwargs):
        if not self or not notification_to_user or not res_id:
            return
        self.ensure_one()
        payload = self.get_notification_payload(notification_to_user, res_id, **kwargs)
        notif_log['payload']= payload
        if self.send_email and kwargs.get('send_notification_email', True):
            if self.template_email:
                values = self.template_email.with_context(notification_to_user=notification_to_user).generate_email(res_id)
                values['recipient_ids'] = [(4, pid) for pid in values.get('partner_ids', list())]
                values['attachment_ids'] = [(4, aid) for aid in values.get('attachment_ids', list())]
                values.pop('partner_ids', None)
                # supaya tidak di tulis di chatter res_id di hapus
                if 'res_id' in values:
                    values.pop('res_id')
            else:
                values = {
                    'subject': payload.get('title'),
                    'body_html': payload.get('body_html') or payload.get('body'),
                    'recipient_ids': [(4, notification_to_user.partner_id.id)]
                }
            result = self.env['mail.mail'].sudo().create(values)
            notif_log['mail_id'] = result.id
            notif_log['mail_model'] = 'mail.mail'
        self.send_chat and self.send_notification_chat(notification_to_user, payload, notif_log, **kwargs)
        self.send_mobile and self.send_notification_mobile(notification_to_user, payload, notif_log, **kwargs)

        return notif_log

    def get_notification_payload(self, notification_to_user, res_id, **kwargs):
        self.ensure_one()
        Template = self.env['mail.template']
        template = self.ensure_one()
        fields = ['title', 'body', 'image', 'body_html', 'body_whatsapp', 'body_telegram']
        notification = {}
        for field in fields:
            Template = Template.with_context(safe=field in {'title'})
            notification[field] = Template._render_template(getattr(template, field), template.model, res_id)
        data = {
            'notification_to_user': notification_to_user.partner_id.email,
        }
        body = notification.pop('body')
        body_html = notification.pop('body_html')
        body_whatsapp = notification.pop('body_whatsapp')
        body_telegram = notification.pop('body_telegram')
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
        url = data.get('url')
        if 'url' not in data and not data.get('url'):
            data['url'] = safe_call_method(transaction_object, 'get_internal_url') or None
        return {
            'notification': eval_context.get('notification'),
            'send_firebase': self.send_firebase,
            'send_whatsapp': self.send_whatsapp,
            'send_telegram': self.send_telegram,
            'data': data,
            'body': body,
            'body_html': body_html,
            'body_whatsapp': body_whatsapp,
            'body_telegram': body_telegram,
            'url': url
        }

    @api.model
    def send_notification_chat(self, notification_to_user, payload, notif_log, **kwargs):
        # payload is firebase format notification
        chat = notification_to_user.send_odoobot_message(
            payload.get('body_html') or payload.get('notification', {}).get('body')
        )
        if chat and notif_log is not None:
            notif_log['chat_id'] = chat.id
            notif_log['chat_model'] = chat._name

    @api.model
    def send_notification_mobile(self, notification_to_user, payload, notif_log, **kwargs):
        pass

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
