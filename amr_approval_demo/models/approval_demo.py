# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.Logger(__name__)


class ApprovalDemo(models.Model):
    _name = 'approval.demo'
    _inherit = [_name, 'approval.instance.able.mixin']
