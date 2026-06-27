# -*- coding: utf-8 -*-

from odoo import api, fields, models
import json
import traceback


class MobileNotificationClient(models.Model):
    _name = "mobile.notification.client"
    _rec_name = 'title'
    _order = 'id desc'

    state = fields.Selection([
        ('accept', 'Accept'),
        ('error', 'Error'),
        ('outgoing', 'Outgoing'),
        ('done', 'Done'),
        ('cancel', 'Cancel'),
    ], default='accept')

    notification_type = fields.Selection(
        [('approval', 'Approval'),
         ('info', 'Info')],
        default='approval'
    )

    to_user_id = fields.Many2one('res.users')

    title = fields.Char()
    body = fields.Text()
    image = fields.Char(help="image urls")

    source_application = fields.Char()
    source_model = fields.Char()
    source_res_id = fields.Integer()
    accept_data = fields.Text()
    payload = fields.Text()
    errors_message = fields.Text()
    last_error = fields.Datetime()
    response = fields.Text()

    def create_payload(self, **kwargs):
        accept_data = json.dumps(kwargs)
        return self.create([{
            'accept_data': accept_data
        }])[0]

    # -------------------------------------------------------
    # SEND
    # -------------------------------------------------------

    def get_mobile_notification_path(self):
        return "/api/intra/mobile/notification"

    def get_server_auth(self):
        server_auth_id = int(
            self.env['ir.config_parameter']
            .sudo()
            .get_param('mobile_notification_server_id', 0)
        )

        return self.env['service.endpoint'].browse(server_auth_id)

    def send(self):
        self.ensure_one()
        payload = {}
        try:
            payload.update(json.loads(self.accept_data or "{}"))
            data = payload.get('data') or {}
            payload['data'] = self.prepare_send_data(**data)
            payload['notification'] = {
                'title': self.title or None,
                'body': self.body or None,
                'image': self.image or None,
            }
            server_auth = self.get_server_auth()
            with server_auth.get_service_client() as s:
                response = s.post(path=self.get_mobile_notification_path(), payload=payload)
                # response = requests.post(url, data=json.dumps(payload), headers=headers)
                response.raise_for_status()
                self.write({
                    'response': response.text,
                    'payload': json.dumps(payload),
                    'state': 'done'
                })
                return True

        except Exception:
            stack = traceback.format_exc()
            self.write({
                'payload': json.dumps(payload),
                'state': 'error',
                'errors_message': stack,
                'last_error': fields.Datetime.now(),
            })
            return False

    def cron_send(self):
        records = self.search([('state', '=', 'outgoing')], limit=1000)
        for rec in records:
            rec.send()

    def mark_outgoing(self):
        self.write({'state': 'outgoing'})

    def cancel(self):
        self.write({'state': 'cancel'})

    def dispatch_send(self):
        self.send()

    # -------------------------------------------------------
    # PROCESS ACCEPT DATA
    # -------------------------------------------------------
    def process(self):
        self.ensure_one()
        try:
            accept_data = json.loads(self.accept_data or "{}")
            mobile_notification = {}
            notification = accept_data.get('notification') or {}
            if notification and isinstance(notification, dict):
                notification_fields = {
                    'title',
                    'body',
                    'image',
                }
                mobile_notification.update({k: v for k, v in notification.items() if k in notification_fields})
            data = accept_data.get('data') or {}
            notification_to_user = None
            if data and isinstance(data, dict):
                allowed_fields = {
                    'notification_type',
                    'source_application',
                    'source_model',
                    'source_res_id'
                }
                mobile_notification.update({k: v for k, v in data.items() if k in allowed_fields})
                notification_to_user = data.get('notification_to_user')
            if notification_to_user:
                to_user_id = self.to_user_id.search(
                    ['|', ('partner_id.email', '=', notification_to_user), ('login', '=', notification_to_user)],
                    limit=1)
            else:
                raise ValueError("notification_to_user not found")

            if to_user_id:
                mobile_notification['to_user_id'] = to_user_id.id
            else:
                raise ValueError("User not found")
            self.write({**mobile_notification, 'state': 'outgoing'})

        except Exception:
            stack_trace = traceback.format_exc()
            self.write({
                'errors_message': stack_trace,
                'state': 'error',
                'last_error': fields.Datetime.now(),
            })

    # -------------------------------------------------------
    # SEND PAYLOAD
    # -------------------------------------------------------
    def prepare_send_data(self, **data):
        data_notif = {k: str(v) for k, v in data.items()}
        data_notif.update(
            {
                "notification_type": str(self.notification_type),
                "source_application": str(self.source_application),
                "source_model": str(self.source_model),
                "source_res_id": str(self.source_res_id),
                "request_datetime": fields.Datetime.to_string(self.create_date)
            }
        )
        if self.to_user_id.partner_id.email:
            data_notif['notification_to_user'] = self.to_user_id.partner_id.email
        return data_notif
