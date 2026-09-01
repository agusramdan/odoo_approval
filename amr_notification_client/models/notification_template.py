# -*- coding: utf-8 -*-

import logging
import traceback

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


# def have_method(obj, method):
#     return hasattr(obj, method) and callable(getattr(obj, method))

class NotificationTemplate(models.Model):
    _inherit = "notification.template"

    def get_notification_client(self, method="POST"):
        server_auth_id = int(
            self.env['ir.config_parameter']
            .sudo()
            .get_param('notification_server_endpoint', 0)
        )
        service_code = self.env['service.endpoint'].browse(server_auth_id)
        return self.env["service.client"].get_service_client(service_code, method=method)

    def send_notification_mobile(self, notification_to_user, payload, notif_log, **kwargs):
        _logger.info("call send_notification_mobile")
        try:
            client = self.get_notification_client()
            client_message = client.prepare_payload(**payload)
            mobile = client_message.dispatch_send()
            if mobile and notif_log is not None:
                notif_log['mobile_id'] = mobile.id
                notif_log['mobile_model'] = mobile._name
        except Exception as e:
            stack_trace = traceback.format_exc()
            notif_log.update(
                mobile_id=0,
                mobile_model=False,
                mobile_error=stack_trace
            )
        return notif_log