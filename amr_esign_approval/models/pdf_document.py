# -*- coding: utf-8 -*-

from odoo import models, _


class PdfDocument(models.Model):
    _name = 'pdf.document'
    # _inherit = [_name, 'approval.auto.register.mixin']
    _inherit = [_name, 'approval.instance.able.mixin']
