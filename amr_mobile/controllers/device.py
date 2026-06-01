# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request
from .mixin import ApiControllerMixin


class DeviceController(http.Controller, ApiControllerMixin):

    @http.route("/api/v1/device/register", type="http", auth="jwt_mobile", methods=["POST"], csrf=False, )
    def register_device(self):

        try:
            payload = self.get_json_payload()
            service = request.env["mobile.service"].sudo()
            result = service.register_device(payload, )
            return self.json_response({
                "success": True,
                "data": result,
            })

        except Exception as ex:
            return self.handle_exception(ex)

    @http.route("/api/v1/device/logout", type="http", auth="jwt_mobile", methods=["POST"], csrf=False, )
    def logout_device(self, **kwargs):

        try:
            payload = self.get_json_payload()
            service = request.env["mobile.service"].sudo()
            result = service.logout_device(payload, )
            return self.json_success(result)
        except Exception as ex:
            return self.handle_exception(ex)

    @http.route("/api/v1/device/revoke", type="http", auth="jwt_mobile", methods=["POST"], csrf=False, )
    def revoke_device(self, **kwargs):

        try:
            payload = self.get_json_payload()
            service = request.env["mobile.service"].sudo()
            result = service.revoke_device(payload, )
            return self.json_success(result)
        except Exception as ex:
            return self.handle_exception(ex)
