# Copyright 2021 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from functools import partial

import jwt  # pylint: disable=missing-manifest-dependency
from jwt import PyJWKClient
from werkzeug.exceptions import InternalServerError

from odoo import _, api, fields, models, tools
from odoo.exceptions import ValidationError

from odoo.addons.auth_jwt.exceptions import (
    AmbiguousJwtValidator,
    JwtValidatorNotFound,
    UnauthorizedInvalidToken,
    UnauthorizedPartnerNotFound,
)

_logger = logging.getLogger(__name__)


class AuthJwtValidator(models.Model):
    _inherit = "auth.jwt.validator"

    audience = fields.Char(
        required=True, help="Comma separated list of audiences, to validate aud."
    )
    issuer = fields.Char(required=True, help="To validate iss.")
    user_id_strategy = fields.Selection(
        selection_add = [('user_match', 'User Match')]
    )
    static_user_id = fields.Many2one("res.users", default=1)
    partner_id_strategy = fields.Selection([("email", "From email claim")])
    partner_id_required = fields.Boolean()

    def _get_uid(self, payload):
        if self.user_id_strategy == 'user_match':
            user = self.env['amr.resource.helper'].get_user_match(payload)
            if user:
                return user.id
        return super()._get_uid(payload)

    @api.model
    def get_validator(self, validator_name,issuer,algorithm):
        validator = self.search([
            ('signature_type','=','public_key'),
            ('public_key_algorithm', '=', algorithm)
        ])
        if len(validator) != 1:
            _logger.error(
                "More than one JWT validator found for name %r", validator_name
            )
            raise AmbiguousJwtValidator()
        return validator

    def get_audience(self):
        return self.audience.split(",") + self.env['amr.resource.helper'].get_audiences()

    @api.model
    def decode(self, token):
        header = jwt.get_unverified_header(token)
        algorithm = header.get('alg')
        if algorithm.startswith('HS'):
            domain =[
                ('signature_type', '=', 'public_key'),
                ('public_key_algorithm', '=', algorithm)
            ]
        else:
            domain = [
                ('signature_type', '=', 'secret'),
                ('public_key_algorithm', '=', algorithm)
            ]
        payload = jwt.decode(
            token,
            options={
                "verify_signature": False
            }
        )
        issuer = payload.get('iss')
        domain.append(('issuer','=',issuer))
        records = self.sudo().search(domain)
        for rec in records:
            try:
                payload = rec._decode(token)
                payload['kid'] = header.get('kid')
                payload['alg'] = algorithm
                return payload
            except :
                pass
        raise UnauthorizedInvalidToken()

    def _decode(self, token):
        """Validate and decode a JWT token, return the payload."""
        if self.signature_type == "secret":
            key = self.secret_key
            algorithm = self.secret_algorithm
        else:
            try:
                header = jwt.get_unverified_header(token)
            except Exception as e:
                _logger.info("Invalid token: %s", e)
                raise UnauthorizedInvalidToken()
            key = self._get_key(header.get("kid"))
            algorithm = self.public_key_algorithm
        try:
            payload = jwt.decode(
                token,
                key=key,
                algorithms=[algorithm],
                options=dict(
                    require=["exp", "aud", "iss"],
                    verify_exp=True,
                    verify_aud=True,
                    verify_iss=True,
                ),
                audience=self.get_audience(),
                issuer=self.issuer,
            )
        except Exception as e:
            _logger.info("Invalid token: %s", e)
            raise UnauthorizedInvalidToken()
        return payload

