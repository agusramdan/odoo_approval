# -*- coding: utf-8 -*-

from odoo import models

import logging

_logger = logging.getLogger(__name__)


class UserDelegation(models.Model):
    _inherit = 'user.delegation'
