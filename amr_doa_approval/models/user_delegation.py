# -*- coding: utf-8 -*-

class UserDelegation(models.Model):
    _name = 'user.delegation'
    _inherit = [_name, 'approval.instance.able.mixin']

