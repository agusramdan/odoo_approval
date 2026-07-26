# -*- coding: utf-8 -*-

import json
import logging
import traceback

from odoo import api, fields, models
from ..tools.utils import safe_call_method, have_method
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval, test_python_expr
from odoo.tools.misc import clean_context
from odoo.tools import plaintext2html

_logger = logging.getLogger(__name__)

DEFAULT_PYTHON_CODE = """# Available variables:
#  - env: Odoo Environment on which the action is triggered
#  - notification
#  - data : data part notification firebase
#  - layout : data for email layout 
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
    notes_chatter = fields.Boolean("Note Chatter", default=False)
    sudo_generate_email = fields.Boolean(
        "Sudo Email Gen", default=True, help="using sudo when generate template email"
    )
    send_email = fields.Boolean("Send Email", default=False)
    send_chat = fields.Boolean("Send Chat", default=False)
    body_chat = fields.Text()
    send_firebase = fields.Boolean("Send Firebase", default=False)
    send_whatsapp = fields.Boolean("Send Whatsapp", default=False)
    send_telegram = fields.Boolean("Send Telegram", default=False)
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
    template_email = fields.Many2one('mail.template')
    approval_email_layout_xmlid = fields.Many2one(
        'ir.model.data',
        string='Email Layout',
        domain="[('model', '=', 'ir.ui.view')]",
        help="email layout used by Approval."
             "Company : amr_approval.approval_email_layout_xmlid\n"
             "system parameter set to: amr_approval.approval_email_layout_xmlid\n"
             "default : mail.mail_notification_light"
    )

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

    def ensure_res_id(self, **kwargs):
        if not self:
            return None
        self.ensure_one()
        _logger.info('Using model %s.', self.model )
        if self.model == 'approval.task':
            approval_task = kwargs.get('approval_task')
            if isinstance(approval_task, models.Model):
                _logger.info('approval_task id %s , %s ', approval_task.transaction_model_name, approval_task)
                return approval_task.id

        if self.model == 'approval.instance':
            approval_instance = kwargs.get('approval_instance')
            if isinstance(approval_instance, models.Model):
                _logger.info('Instance id %s , %s ',approval_instance.transaction_model_name,approval_instance)
                return approval_instance.id

        # check transaction_object
        transaction_object = kwargs.get('transaction_object')
        if transaction_object and isinstance(transaction_object, models.Model):
            if transaction_object._name == self.model:
                _logger.info('transaction_object id %s , %s ', self.model, transaction_object)
                return transaction_object.id
        _logger.warning("Not transaction_object %s", transaction_object)

        # check approval_task_line
        approval_task_line = kwargs.get('approval_task_line')
        if approval_task_line and isinstance(approval_task_line, models.Model):
            if approval_task_line._name == self.model:
                _logger.info('approval_task_line id %s , %s ', self.model, transaction_object)
                return approval_task_line.id
        _logger.warning("Not approval_task_line %s", approval_task_line)

        transaction_id = kwargs.get("transaction_id")
        transaction_model_name = kwargs.get("transaction_model_name")
        if transaction_id and transaction_model_name and transaction_model_name == self.model:
            return transaction_id
        return None

    def send_notification_to_users(self, users, res_id=None, **kwargs):
        if not self:
            _logger.warning("No template setup")
            return
        self.ensure_one()
        if not users:
            _logger.warning("no user %s", users)
            return
        old_res_id = res_id
        res_id = self.ensure_res_id(**kwargs) or old_res_id
        if old_res_id != res_id:
            _logger.info('Change old_res_id %s -> %s',old_res_id, res_id)
        if not res_id:
            _logger.info("no res_id %s", res_id)
            return

        try:
            data = self.env[self.model].browse(res_id).exists()
        except Exception:
            _logger.warning("data remove %s , %s.", self.model, data.id)
            return

        if not data:
            _logger.warning("data remove %s , %s.", self.model, data.id)
            return

        notification_log = self.env['notification.log'].browse()
        for notification_to_user in users:
            notif_log = {
                "res_id": res_id,
                "user_id": self.env.user.id,
                "transaction_id": kwargs.get("transaction_id"),
                "transaction_model_name": kwargs.get("transaction_model_name"),
            }
            try:
                with self.env.cr.savepoint():
                    notif_log = self.send_notification_to_user(notification_to_user, res_id, notif_log, **kwargs)
            except Exception:
                stack_trace = traceback.format_exc()
                notif_log.update(
                    notif_error=stack_trace
                )
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
        payload_error = payload.pop('payload_error', None)
        notif_log['payload'] = json.dumps(payload)
        notif_log['payload_error'] = payload_error
        self.send_notification_payload(notification_to_user, payload, notif_log, **kwargs)

        return notif_log

    @api.model
    def prepare_data_eval_context(self, data, notification_to_user=None, res_id=None, **kwargs):

        return data

    def get_chatter_message(self, res_id=False, **kwargs):
        _logger.info('get_chatter_message')
        new_res_id = self.ensure_res_id(**kwargs) or res_id
        if new_res_id != new_res_id:
            _logger.info("change res_id from %s to %s", res_id, new_res_id)
            res_id = new_res_id

        if not res_id or not self.env[self.model].sudo().browse(res_id):
            _logger.warning("data %s and %s", self.model, res_id)
            return ""
        template = self.ensure_one()
        ctx = clean_context(self.env.context)
        # v13
        renderer = self.env['mail.template'].sudo().with_context(ctx)
        # v16
        # renderer = self.env['mail.render.mixin'].sudo().with_context(ctx)
        try:
            # v16
            # if field in ['body_html', 'body_chat']:
            #     engine = "qweb"
            # else:
            #     engine = 'inline_template'
            # request[field] = renderer._render_template(
            #     getattr(template, field), template.model, [res_id], engine=engine,
            # )[res_id]
            # v13
            return renderer._render_template(template.body_chatter, template.model, res_id)
        except Exception:
            _logger.exception("field body_chatter", )
            return ""

    def get_notification_payload(self, notification_to_user, res_id, **kwargs):
        _logger.info('get_notification_payload')
        if not res_id or not self.env[self.model].sudo().browse(res_id):
            _logger.warning("data %s and %s", self.model, res_id)
            return {}
        template = self.ensure_one()
        ctx = clean_context(self.env.context)
        ctx['notification_to_user'] = notification_to_user
        # Template = self.env['mail.template'].sudo().with_context(ctx)
        # fields = ['title', 'body', 'image', 'body_html', 'body_chat', 'body_whatsapp', 'body_telegram']
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
            'notification_to_user': email,
            'notification_to_partner_id': notification_to_user.partner_id.id,
            'notification_to_user_id': notification_to_user.id,
            'notification_to_email': email
        }
        request = self.prepare_data_eval_context(request, notification_to_user, res_id, **kwargs) or request
        # template = self
        ctx = clean_context(self.env.context)
        ctx['notification_to_user'] = notification_to_user
        # template = self
        fields_ = ['title', 'body', 'image', 'body_html', 'body_chat', 'body_whatsapp', 'body_telegram']
        # v13
        Template = self.env['mail.template'].sudo().with_context(ctx)
        # v16
        # renderer = self.env['mail.render.mixin'].sudo().with_context(ctx)
        payload_error = []
        for field in fields_:
            try:
                # v16
                # if field in ['body_html', 'body_chat']:
                #     engine = "qweb"
                # else:
                #     engine = 'inline_template'
                # request[field] = renderer._render_template(
                #     getattr(template, field), template.model, [res_id], engine=engine,
                # )[res_id]
                # v13
                renderer = Template.with_context(safe=field in {'title'})
                request[field] = renderer._render_template(getattr(template, field), template.model, res_id)
            except Exception:
                payload_error.append(traceback.format_exc())
                _logger.exception("field %s", field)
                continue

        eval_context = self._get_eval_context()
        approval_task_line = kwargs.get('approval_task_line')
        if approval_task_line and isinstance(approval_task_line, models.BaseModel):
            request['source_approval_model'] = approval_task_line._name
            request['source_approval_res_id'] = approval_task_line.id
        transaction_object = kwargs.get('transaction_object')
        if transaction_object and isinstance(transaction_object, models.BaseModel):
            request['source_model'] = transaction_object._name
            request['source_res_id'] = transaction_object.id
        record = self.env[self.model].sudo().browse(res_id)
        eval_context['object'] = eval_context['record'] = record
        eval_context['notification'] = {
            'title': request.get('title', ''),
            'body': request.get('body', ''),
            'image': request.get('image', ''),
        }
        eval_context['data'] = request
        eval_context = self._run_action_code_multi(eval_context)
        data = eval_context.get('data') or {}
        layout = eval_context.get('layout') or {}
        if transaction_object and 'url' not in data and not data.get('url'):
            data['url'] = safe_call_method(transaction_object, 'get_internal_url') or None
        data.update(eval_context.get('notification') or {})
        if 'amr.resource.helper' in self.env:
            data['source_application'] = self.env['amr.resource.helper'].get_issuer()
        _logger.info("Phone number %s. ", data.get('phone'))
        if payload_error:
            data['payload_error'] = str(payload_error)
        data['layout'] = layout
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
    def render_qweb_template(self, xmlid, values):
        View = self.env['ir.ui.view']

        if hasattr(View, '_render_template'):
            return View._render_template(xmlid, values)

        return self.env.ref(xmlid).render(values)

    @api.model
    def send_notification_email(self, notification_to_user, payload, notif_log, **kwargs):
        # payload is firebase format notification
        if not self.send_email:
            return notif_log
        res_id = kwargs.get('res_id') or payload.get('res_id')
        if not res_id:
            _logger.warning("res_id not set %s", res_id)
            return notif_log
        if res_id:
            record = self.env[self.model].sudo().browse(res_id)
            if not record:
                _logger.warning("res_id not found %s", res_id)
                return notif_log
        else:
            _logger.warning("res_id not set %s", res_id)
            return notif_log
        values = {}

        company = getattr(record, 'company_id') or self.get_company(**kwargs) or self.env.company
        kwargs.setdefault('company', company)
        layout_xmlid = self.sudo().get_approval_email_layout_xmlid(**kwargs)
        enhance_layout = bool(layout_xmlid)
        if self.template_email:
            try:
                ctx = dict(clean_context(self.env.context))
                ctx['notification_to_user'] = notification_to_user
                _logger.info("after ctx %s ", ctx)
                if self.sudo_generate_email:
                    # generate email perlu sudo.
                    # tanpa itu akan terjadi error access data.
                    # karena beberapa data (seperti user,company tidak bisa diakses)
                    template = self.template_email.sudo().with_context(ctx)
                else:
                    template = self.template_email.with_context(ctx)
                values = template.generate_email([res_id], self.get_email_fields())[res_id]
                enhance_layout = True
            except Exception:
                stack_trace = traceback.format_exc()
                notif_log.update(
                    mail_id=0,
                    mail_model=False,
                    mail_error=stack_trace
                )
                _logger.exception("process %s , %s", self.model, res_id)

        if not values:
            body = payload.get('body', None)
            body_html = payload.get('body_email', None) or payload.get('body_html', None)
            enhance_layout = not payload.get('body_email_generate_with_layout', None)
            if not body_html and body:
                body_html = plaintext2html(body)
            if not body_html:
                notif_log.update(
                    mail_id=0,
                    mail_model=False,
                    mail_error="No body_html can generate. Skip send email"
                )
            values = {
                'subject': payload.get('title', None),
                'body_html': body_html,
                'body': body,
                'auto_delete': self.auto_delete,
            }

        if enhance_layout and values.get('body_html') and layout_xmlid:
            layout_data = dict(payload.get('layout') or {})
            record_name = values.get('record_name')
            if have_method(record, 'get_internal_document'):
                document = record.get_internal_document()
            else:
                document = record._description
            if not record_name:
                if have_method(record, 'get_internal_number'):
                    record_name = record.get_internal_document()
                else:
                    record_name = values.get('ref') or record.display_name
            message_data = {
                'body': values.get('body_html'),
                'subject': values.get("subject"),
                'record_name': record_name,
                'model': self.model,
                'res_id': res_id,
                'author_id': self.env.user.partner_id.id,
            }
            message = self.env['mail.message'].new(message_data)
            layout_data.update({
                'message': message,
                'company': company,
                'document': document,
            })
            body_html = self.sudo().render_qweb_template(layout_xmlid, layout_data)
            values['body_html'] = body_html

        self.setup_email_values(values)
        values['recipient_ids'] = [(4, notification_to_user.partner_id.id)]
        # supaya tidak di tulis di chatter res_id di hapus
        values.pop('res_id', None)
        ctx = clean_context(self.env.context)
        try:
            with self.env.cr.savepoint():
                result = self.env['mail.mail'].with_context(ctx).sudo().create(values)
                notif_log['mail_id'] = result.id
                notif_log['mail_model'] = 'mail.mail'
        except Exception as e:
            stack_trace = traceback.format_exc()
            notif_log.update(
                mail_id=0,
                mail_model=False,
                mail_error=stack_trace
            )
        return notif_log

    @api.model
    def send_notification_chat(self, notification_to_user, payload, notif_log, **kwargs):
        if not self.send_chat:
            return notif_log
        # payload is firebase format notification
        try:
            with self.env.cr.savepoint():
                body_chat = payload.pop('body_chat', None) or payload.get('body_html') or payload.get('body')
                chat = notification_to_user.send_odoobot_message(
                    body_chat
                )
                if chat and notif_log is not None:
                    notif_log['chat_id'] = chat.id
                    notif_log['chat_model'] = chat._name
        except Exception as e:
            stack_trace = traceback.format_exc()
            notif_log.update(
                chat_id=0,
                chat_model=False,
                chat_error=stack_trace
            )
        return notif_log

    @api.model
    def send_notification_mobile(self, notification_to_user, payload, notif_log, **kwargs):
        if not self.send_mobile:
            return notif_log

        if 'mobile.notification.client' in self.env:
            try:
                with self.env.cr.savepoint():
                    mobile_notification_client = self.env['mobile.notification.client']
                    notif = mobile_notification_client.create_payload(to_user_id=notification_to_user.id, **payload)
                    notif.process()
                    if notif and notif_log is not None:
                        notif_log['mobile_id'] = notif.id
                        notif_log['mobile_model'] = notif._name
                    notif.dispatch_send()
            except Exception as e:
                stack_trace = traceback.format_exc()
                notif_log.update(
                    mobile_id=0,
                    mobile_model=False,
                    mobile_error=stack_trace
                )
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
        else:
            _logger.info("Tidak ada message_post %s ", transaction_object)
        return

    def get_company(self, **kwargs):
        def ensure_object(obj):
            if isinstance(obj, models.BaseModel):
                return obj
            if isinstance(obj, int):
                return self.env['res.company'].browse(obj)
            return self.env['res.company'].browse()

        return ensure_object(kwargs.get('company') or kwargs.get('company_id'))

    def get_approval_email_layout_xmlid(self, **kwargs):
        self.ensure_one()
        layout = self.approval_email_layout_xmlid

        if not layout:
            layout = self.get_company(**kwargs).approval_email_layout_xmlid

        if layout:
            return layout.complete_name

        # 3. Global
        xmlid = self.env['ir.config_parameter'].sudo().get_param(
            'amr_approval.approval_email_layout_xmlid'
        )
        if xmlid:
            return xmlid

        # 4. Default sesuai versi
        return 'mail.mail_notification_light'
