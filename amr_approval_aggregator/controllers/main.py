# -*- coding: utf-8 -*-

import logging
import json
import werkzeug

from datetime import datetime, date
from odoo import api, http, SUPERUSER_ID, _, registry as registry_get
from odoo.fields import Datetime, Date, Many2many, One2many
from odoo.exceptions import AccessError
from odoo.http import request

_logger = logging.getLogger(__name__)


class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (bytes, bytearray)):
            return obj.decode("utf-8")
        if isinstance(obj, datetime):
            return Datetime.to_string(obj)
        if isinstance(obj, date):
            return Date.to_string(obj)
        return super().default(obj)


def get_body_json():
    data = {}
    data_str = request.httprequest.data.decode("utf-8")
    if data_str:
        try:
            data = json.loads(data_str)
            if isinstance(data, str):
                data = json.loads(data)
        except:
            pass
    return data


def valid_response(status, data):
    return werkzeug.wrappers.Response(
        status=status,
        content_type='application/json; charset=utf-8',
        response=json.dumps(data, cls=JSONEncoder),
    )


def invalid_response(status, error, info=""):
    return werkzeug.wrappers.Response(
        status=status,
        content_type='application/json; charset=utf-8',
        response=json.dumps({
            'error': error,
            'error_description': info,
        }),
    )


class MainController(http.Controller):

    @http.route(['/api/v1/approval/aggregator', '/api/intra/mobile/approval'], methods=['POST'], type='http',
                auth='machine', csrf=False)
    def post_approval(self, **post):
        data = post or get_body_json()
        if not data:
            return invalid_response(400, "no_data", "enpty data")
        new_registry = registry_get(request.session.get('db'))
        with new_registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            result = env['approval.task.request'].api_create_request(**data)

        return valid_response(200, result)

    @http.route(['/api/v1/approval/aggregator', '/api/intra/mobile/approval'], methods=['GET'], type='http',
                auth='machine', csrf=False)
    def get_approval(self, **post):
        data = post
        new_registry = registry_get(request.session.get('db'))
        with new_registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            result = env['approval.task.aggregator'].api_get_approvals(**data)
        return valid_response(200, result)

    @http.route(['/api/v1/approval/aggregator/distinct', '/api/intra/mobile/approval/distinct'], methods=['GET'],
                type='http', auth='machine', csrf=False)
    def get_approval_distinct(self, **post):
        data = post
        new_registry = registry_get(request.session.get('db'))
        with new_registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})

            if 'user_email' in data:
                domain = [('user_id.partner_id.email', '=', data['user_email'])]
            else:
                domain = []

            if 'field_select' not in data:
                return invalid_response(400, "field_select parameter not found", "Invalid data query")
            else:
                field_select = data['field_select']

            result_group = env['approval.task.aggregator'].read_group(
                domain=domain,
                fields=[field_select],
                groupby=[field_select],
                lazy=False
            )
            result = [str(rec.get(field_select, "")) for rec in result_group]
        return valid_response(200, result)
