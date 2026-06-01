# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request, route
from ..exceptions.api_exception import ApiException
from .mixin import ApiControllerMixin


class NotificationController(http.Controller, ApiControllerMixin):

    @route("/api/v1/notification/send", type="http", auth="jwt_notification", methods=["POST"], csrf=False, )
    def send_notification(self, **kwargs):

        try:
            payload = self.get_json_payload()
            result = request.env["amr.notification.service"].sudo().send_notification(payload,)
            return self.json_success(result)
        except Exception as ex:
            return self.handle_exception(ex)

    @route(
        "/api/v1/notification/topic/send", type="http", auth="jwt_notification", methods=["POST"], csrf=False,
    )
    def send_topic_notification(self, **kwargs):
        try:
            payload = self.get_json_payload()
            result = request.env["amr.notification.service"].sudo().send_topic_notification(
                payload,
            )
            return self.json_success(result)
        except Exception as ex:
            return self.handle_exception(ex)
