# -*- coding: utf-8 -*-

import base64
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare
from odoo.tools.safe_eval import safe_eval, test_python_expr
from pytz import timezone

_logger = logging.getLogger(__name__)


class ApprovalDocument(models.Model):
    _inherit = 'approval.document'

    pdf_sign_template_id = fields.Many2one('pdf.sign.template')

    @api.model
    def _get_pdf_eval_context(self, approval_instance):
        eval_context = super(ApprovalDocument, self)._get_pdf_eval_context(approval_instance)
        eval_context['pdf_document'] = approval_instance and approval_instance.pdf_document_id
        return eval_context

    def get_config_pdf_document(self, approval_instance):
        _logger.info("call create_or_update_pdf_document")
        config = super(ApprovalDocument, self).get_config_pdf_document(approval_instance)
        if isinstance(config, dict) and self.pdf_sign_template_id:
            config['template_id'] = self.pdf_sign_template_id.id
        return config
