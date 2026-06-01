# -*- coding: utf-8 -*-

from werkzeug.exceptions import Unauthorized
from odoo import api, models
from odoo.http import request
from odoo.service import security


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _auth_method_jwt_notification(cls):
        # Menggunakan token oidc untuk handle API call
        heleper = request.env['amr.resource.helper'].sudo()
        token = heleper.get_bearer_token()
        # VALIDASI TOKEN
        validate = heleper.get_validate_user(token)
        if not validate:
            raise Unauthorized('Invalid Token')

        user = heleper.get_user_match(validate)

        if not user:
            raise Unauthorized('User not found')

        if request.uid != user.id:
            request.uid = user.id
            request.jwt_token = token
            request.jwt_payload = validate
