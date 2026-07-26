import os

import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class HrExpenseSheet(models.Model):
    _name = "hr.expense.sheet"
    _inherit = [_name, 'approval.instance.able.mixin']
