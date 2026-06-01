# -*- coding: utf-8 -*-

import logging
import jwt
import requests
import re

from jwt import PyJWKClient, InvalidTokenError
from odoo import api, fields, models
from odoo.http import request

_logger = logging.getLogger(__name__)

AUTHORIZATION_RE = re.compile(r"^Bearer ([^ ]+)$")


class ResourceAccessToken(models.AbstractModel):
    _name = 'amr.resource.helper'
    _description = 'Resource Server'

    @api.model
    def is_local_issuer(self, issuer):
        return self.env['ir.config_parameter'].sudo().get_param('web.base.url') == issuer

    @api.model
    def get_issuer(self):
        config_param = self.env['ir.config_parameter'].sudo()
        issuer = config_param.get_param('amr_resource.issuer', 'web.base.url')
        return config_param.get_param(issuer) or config_param.get_param('web.base.url')

    @api.model
    def get_audience(self):
        config_param = self.env['ir.config_parameter'].sudo()
        amr_resource_audience = config_param.get_param('amr_resource.audience', 'web.base.url')
        return config_param.get_param(amr_resource_audience) or config_param.get_param('web.base.url')

    @api.model
    def get_audiences(self, issuer=None):
        return [self.get_audience()]

    @api.model
    def get_oidc_config(self, issuer):
        url = issuer.rstrip('/') + '/.well-known/openid-configuration'
        response = requests.get(url)
        response.raise_for_status()
        return response.json()

    @api.model
    def get_jwks_data(self, issuer):
        url = issuer.rstrip('/') + '/.well-known/jwks.json'
        response = requests.get(url)
        response.raise_for_status()
        return response.json()

    def encode(self, **kw):
        response = self.generate_token(**kw)
        return response.get('access_token')

    def decode(self, token, **kw):
        return self.validate(token)

    @api.model
    def generate_token(self, client_id=None, client_secret=None, iss=None, issuer=None, issuer_url=None, **kw):
        issuer_url = iss or issuer or issuer_url
        if not issuer_url:
            raise ValueError('Issuer (iss) is required')
        oidc_config = self.get_oidc_config(issuer_url)
        token_endpoint = oidc_config.get('token_endpoint')
        if client_id and client_secret:
            auth = (client_id, client_secret)
        else:
            auth = None
        response = requests.post(token_endpoint, data=kw, auth=auth)
        response.raise_for_status()
        return response.json()

    @api.model
    def introspect_token(self, token, client_id=None, client_secret=None, url=None, iss=None, **kw):
        if not url:
            if not iss:
                payload = jwt.decode(token, options={"verify_signature": False})
                iss = payload.get('iss')
            oidc_config = self.get_oidc_config(iss)
            url = oidc_config.get('introspection_endpoint')

        if not url:
            raise ValueError('Introspection endpoint URL is required')

        if client_id and client_secret:
            auth = (client_id, client_secret)
        else:
            auth = None
        # response = requests.get(url, param={'access_token': token}, auth=auth)
        response = requests.get(url, data={'access_token': token}, auth=auth)
        response.raise_for_status()
        return response.json()

    @api.model
    def validate_hs(self, token, **kw):
        result = self.introspect_token(token, **kw)
        if not result.get('active'):
            raise InvalidTokenError('Token is not active')
        return result

    # helper will call from Controller
    @api.model
    def validate(self, token):
        header = jwt.get_unverified_header(token)
        alg = header.get('alg')
        if alg.startswith('HS'):
            _logger.warning("Token signed with HS algorithm, validating via introspection endpoint")
            return self.validate_hs(token)
        payload = jwt.decode(
            token,
            options={
                "verify_signature": False,
            },
        )

        issuer = payload.get('iss')
        config = self.get_oidc_config(issuer)
        jwks_client = PyJWKClient(config.get('jwks_uri'))
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=[alg],
            issuer=issuer,
            audience=self.get_audiences(issuer)
        )
        if payload:
            if 'kid' not in payload:
                payload['kid'] = header.get('kid')
            if 'alg' not in payload:
                payload['alg'] = alg
        return payload

    @api.model
    def get_validate_user(self, token):
        validate = self.validate(token)
        return validate or None

    @api.model
    def get_user_match(self, validation):
        email = validation.get('email')
        if email:
            return self.sudo().env['res.users'].search([('email', '=', email)], limit=1)
        return None

    @api.model
    def get_user_token_login(self, token):
        validate = self.sudo().validate(token)
        return self.get_user_match(validate)

    def get_uid(self, payload):
        user = self.get_user_match(payload)
        return user and user.id

    @api.model
    def is_user_match(self, user, payload):
        if not user:
            return False
        uid = self.get_uid(payload)
        return bool(user.id == uid)

    @classmethod
    def get_param_token(cls):
        return request.params.get("access_token") or request.params.get("token")

    @classmethod
    def get_header_token(cls):
        return request.httprequest.headers.get("access_token") or request.httprequest.headers.get("token")

    @classmethod
    def get_bearer_token(cls):
        # https://tools.ietf.org/html/rfc2617#section-3.2.2
        authorization = request.httprequest.environ.get("HTTP_AUTHORIZATION")
        if not authorization:
            _logger.info("Missing Authorization header.")
            return None
        # https://tools.ietf.org/html/rfc6750#section-2.1
        mo = AUTHORIZATION_RE.match(authorization)
        if not mo:
            _logger.info("Malformed Authorization header.")
            return None
        return mo.group(1)
