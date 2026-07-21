# -*- coding: utf-8 -*-
import json
import logging

from odoo import api, fields, models
from ..tools.utils import safe_call_method, have_method
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

    active = fields.Boolean(default=True)
    name = fields.Char("Notification")
    model_id = fields.Many2one('ir.model')
    model = fields.Char(related='model_id.model', store=True)
    auto_delete = fields.Boolean(default=True)
    send_mobile = fields.Boolean(compute="_compute_send_mobile")
    notes_chatter = fields.Boolean("Note Chater", default=False)
    send_email = fields.Boolean("Send Email", default=False)
    send_chat = fields.Boolean("Send Chat", default=False)
    body_chat = fields.Text()
    send_firebase = fields.Boolean("Send Firebase", default=False)
    send_whatsapp = fields.Boolean("Send Whatsapp", default=False)
    send_telegram = fields.Boolean("Send Telegram", default=False)

    template_email = fields.Many2one('mail.template')

    # firebase
    title = fields.Char()
    body = fields.Char()
    image = fields.Char()
    # generic for email or chat or data
    body_html = fields.Text()
    body_whatsapp = fields.Text()
    body_telegram = fields.Text()
    body_chatter = fields.Text()
    code = fields.Text(
        string='Python Code',
        default=DEFAULT_PYTHON_CODE,
        help="Write Python code that the action will execute. Some variables are "
             "available for use; help about python expression is given in the help tab."
    )

    @api.depends(
        "send_firebase",
        "send_whatsapp",
        "send_telegram",
    )
    def _compute_send_mobile(self):
        for rec in self:
            rec.send_mobile = any([
                rec.send_firebase,
                rec.send_whatsapp,
                rec.send_telegram,
            ])

    @api.model_create_multi
    @api.returns('self', lambda value: value.id)
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('model_id'):
                vals['model_id'] = self.model_id.search([('model', '=', vals.get('model'))], limit=1).id
            vals.pop('model', None)
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
        data = self.env[self.model].browse(res_id)
        if not data:
            _logger.warning("data remove %s , %s.", self.model, data.id)
            return
        notification_log = self.env['notification.log'].browse()
        for notification_to_user in users:
            notif_log = {}
            notif_log = self.send_notification_to_user(notification_to_user, res_id, notif_log, **kwargs)
            if notif_log:
                notif_log["res_id"] = res_id
                notif_log["user_id"] = self.env.user.id
                notif_log["receiver_id"] = notification_to_user.id
                notif_log["notification_template_id"] = self.id
                notif_log["transaction_id"] = kwargs.get("transaction_id")
                notif_log["transaction_model_name"] = kwargs.get("transaction_model_name")
                notification_log |= self.env['notification.log'].sudo().create(notif_log)
        return notification_log

    def send_notification_to_user(self, notification_to_user, res_id, notif_log, **kwargs):
        if not self or not notification_to_user or not res_id:
            return
        self.ensure_one()
        notif_log = notif_log or {}
        payload = self.get_notification_payload(notification_to_user, res_id, **kwargs)
        notif_log['payload'] = json.dumps(payload)
        self.send_notification_payload(notification_to_user, payload, notif_log, **kwargs)

        return notif_log

    def prepare_data_eval_context(self, data, notification_to_user=None, res_id=None, **kwargs):

        return data

    def get_notification_payload(self, notification_to_user, res_id, **kwargs):
        if not res_id or not self.env[self.model].sudo().browse(res_id):
            _logger.warning("data %s and %s",self.model,res_id)
            return {}
        template = self.ensure_one()
        Template = self.env['mail.template'].sudo().with_context(notification_to_user=notification_to_user)
        fields = ['title', 'body', 'image', 'body_html', 'body_chat', 'body_whatsapp', 'body_telegram']
        phone_number = notification_to_user.get_phone_number()
        email = notification_to_user.email
        request = {
            'res_id': res_id,
            'send_email': self.send_email,
            'send_chat': self.send_chat,
            'send_mobile': self.send_mobile,
            'send_firebase': self.send_firebase,
            'send_whatsapp': self.send_whatsapp,
            'send_telegram': self.send_telegram,
            'phone': phone_number,
            'email': email,
            'notification_to_partner_id': notification_to_user.partner_id.id,
            'notification_to_user_id': notification_to_user.id,
            'notification_to_email': email
        }
        request = self.prepare_data_eval_context(request, notification_to_user, res_id, **kwargs) or request
        for field in fields:
            Template = Template.with_context(safe=field in {'title'})
            request[field] = Template._render_template(getattr(template, field), template.model, res_id)
        approval_task_line = kwargs.get('approval_task_line')
        if approval_task_line and isinstance(approval_task_line, models.BaseModel):
            request['source_approval_model'] = approval_task_line._name,
            request['source_approval_res_id'] = approval_task_line.id
        eval_context = self._get_eval_context()
        transaction_object = self.env[self.model].sudo().browse(res_id)
        eval_context['object'] = eval_context['record'] = transaction_object
        eval_context['notification'] = {
            'title': request.get('title', ''),
            'body': request.get('body', ''),
            'image': request.get('image', ''),
        }

        eval_context['data'] = request
        eval_context = self._run_action_code_multi(eval_context)
        data = eval_context.get('data') or {}
        if 'url' not in data and not data.get('url'):
            data['url'] = safe_call_method(transaction_object, 'get_internal_url') or None
        data.update(eval_context.get('notification'))
        if 'amr.resource.helper' in self.env:
            data['source_application'] = self.env['amr.resource.helper'].get_issuer()
        data.update({
            'source_res_id': res_id,
            'source_model': self.model,
        })
        return data

    def send_notification_payload(self, notification_to_user, payload, notif_log, **kwargs):
        payload.get('send_email') and self.send_notification_email(notification_to_user, payload, notif_log, **kwargs)
        payload.get('send_chat') and self.send_notification_chat(notification_to_user, payload, notif_log, **kwargs)
        payload.get('send_mobile') and self.send_notification_mobile(notification_to_user, payload, notif_log, **kwargs)
        if payload.get('title'):
            notif_log['name'] = payload.get('title')
        _logger.info("notif_log %s", notif_log)
        return notif_log

    @api.model
    def get_email_fields(self):
        return ['subject', 'body_html', 'auto_delete', 'scheduled_date']
        # return['subject', 'body_html',
        # 'email_from',
        # 'email_cc', 'email_to', 'partner_to', 'reply_to',
        # 'auto_delete', 'scheduled_date']

    @api.model
    def setup_email_values(self, values):
        # values['recipient_ids'] = [(4, pid) for pid in values.get('partner_ids', list())]
        values['attachment_ids'] = [(4, aid) for aid in values.get('attachment_ids', list())]
        # values.pop('partner_ids', None)
        return values

    @api.model
    def send_notification_email(self, notification_to_user, payload, notif_log, **kwargs):
        # payload is firebase format notification
        if self.template_email:
            try:
                template = self.template_email.with_context(notification_to_user=notification_to_user)
                values = template.generate_email([res_id], self.get_email_fields())[res_id]
            except Exception:
                _logger.exception("process %s , %s",self.model,res_id)
        if not values:
            values = {
                'subject': payload.get('title', None),
                'body_html': payload.get('body_email', None) or payload.get('body_html', None) or payload.get('body', None),
                'body': payload.get('body', None),
                'auto_delete': self.auto_delete,
            }
        self.setup_email_values(values)
        values['recipient_ids']= [(4, notification_to_user.partner_id.id)]
        # supaya tidak di tulis di chatter res_id di hapus
        # remove default_res_id context
        values.pop('res_id', None)
        if 'default_res_id' in self.env.context:
            ctx = dict(self.env.context)
            ctx.pop('default_res_id', None)
            result = self.env['mail.mail'].with_context(ctx).sudo().create(values)
        else:
            result = self.env['mail.mail'].sudo().create(values)
        notif_log['mail_id'] = result.id
        notif_log['mail_model'] = 'mail.mail'
        return notif_log

    @api.model
    def send_notification_chat(self, notification_to_user, payload, notif_log, **kwargs):
        if not self.send_chat:
            return notif_log
        # payload is firebase format notification
        body_chat = payload.pop('body_chat', None) or payload.get('body_html') or payload.get('body')
        chat = notification_to_user.send_odoobot_message(
            body_chat
        )
        if chat and notif_log is not None:
            notif_log['chat_id'] = chat.id
            notif_log['chat_model'] = chat._name
        return notif_log

    @api.model
    def send_notification_mobile(self, notification_to_user, payload, notif_log, **kwargs):
        if not self.send_mobile:
            return notif_log

        if 'mobile.notification.client' in self.env:
            mobile_notification_client = self.env['mobile.notification.client']
            notif = mobile_notification_client.create_payload(to_user_id=notification_to_user.id, **payload)
            notif.process()
            if notif and notif_log is not None:
                notif_log['mobile_id'] = notif.id
                notif_log['mobile_model'] = notif._name
            notif.dispatch_send()
        else:
            _logger.warning("Without install mobile notification client addons please.")
        return notif_log

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

    @api.model
    def send_message_post(self, transaction_object, message, **kwargs):
        if not transaction_object:
            return
        if have_method(transaction_object, "message_post"):
            return transaction_object.sudo().message_post(body=message, author_id=self.env.user.partner_id.id)
        return
