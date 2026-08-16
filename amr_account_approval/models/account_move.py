import os

import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = [_name, 'approval.instance.able.mixin']
