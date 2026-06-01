# -*- coding: utf-8 -*-

import logging

from odoo import api, models, tools
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class Base(models.AbstractModel):
    _inherit = 'base'

    def user_machine_sudo(self, user):
        """ with_user(user)

        Return a new version of this recordset attached to the given user_machine, in
        superuser mode
        """
        if not user:
            return self

        if user.is_user_machine():
            return self.with_env(self.env(user=user, su=True))

        return self.with_env(self.env(user=user))


class ResUsers(models.Model):
    _inherit = 'res.users'

    # @tools.ormcache('self.id')
    def is_user_machine(self):
        self.ensure_one()
        return bool(self.has_group('amr_resource.group_machine'))

    # @tools.ormcache('self.id')
    def is_user_technical(self):
        self.ensure_one()
        return bool(self.has_group('amr_resource.group_technical'))

    # @tools.ormcache('self.id')
    def is_user_business(self):
        self.ensure_one()
        return not self.share and not self.is_user_technical() and self.is_user_machine()

    # @tools.ormcache('self.id')
    def is_user_allow_create_token(self):
        self.ensure_one()
        return True

    def decode(self, token, **kw):
        self.ensure_one()
        helper = self.env['amr.resource.helper']
        payload = helper.decode(token, **kw)
        uid = helper.get_uid(payload)
        if uid == self.id:
            return payload
        return None

    def get_access_token(self, **kw):
        if not self.is_user_allow_create_token():
            raise UserError('User not allowed to create access token')

        raise NotImplemented

    def create_access_token(self, **kw):
        if not self.is_user_allow_create_token():
            raise UserError('User not allowed to create access token')

        raise NotImplemented

    @api.model
    def add_url_access_token(self, url=None, **kw):
        return url

    @api.model
    def get_auto_login_url(self, url=None, **kw):
        return url

    def with_access_token_context(self, validate=True):
        helper = self.env['amr.resource.helper']
        if self.env.context.get('__access_token_context'):
            return self
        token = helper.get_bearer_token()
        if not token:
            raise UserError('Without token')
        if validate:
            payload = helper.validate(token)
        uid = helper.get_uid(payload)
        if uid != self.id:
            return self

        return self.env.with_context(__access_token_context=payload)

    # @api.model_create_multi
    # @api.returns('self', lambda value: value.id)
    # def create(self, vals_list):
    #     type(self).is_user_machine.clear_cache(self.env)
    #     type(self).is_user_technical.clear_cache(self.env)
    #     type(self).is_user_business.clear_cache(self.env)
    #     return super(ResUsers, self).create(vals_list)
    #
    # def write(self, vals):
    #     type(self).is_user_machine.clear_cache(self.env)
    #     type(self).is_user_technical.clear_cache(self.env)
    #     type(self).is_user_business.clear_cache(self.env)
    #     return super(ResUsers, self).write(vals)
