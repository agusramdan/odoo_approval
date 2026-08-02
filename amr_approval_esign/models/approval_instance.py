# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import datetime

_logger = logging.getLogger(__name__)


class ApprovalInstance(models.Model):
    _inherit = 'approval.instance'

    pdf_document_id = fields.Many2one('pdf.document')

    pdf_file = fields.Binary('PDF File', related='pdf_document_id.pdf_file')
    pdf_filename = fields.Char('PDF Filename', related='pdf_document_id.pdf_filename')
    pdf_hash = fields.Char('PDF Hash', readonly=True, related='pdf_document_id.pdf_hash')

    pdf_lock_file = fields.Binary('Lock Lock', readonly=True, related='pdf_document_id.pdf_lock_file')
    pdf_lock_filename = fields.Char('Lock Filename', related='pdf_document_id.pdf_lock_filename')
    pdf_lock_hash = fields.Char('Lock Hash', readonly=True, related='pdf_document_id.pdf_lock_hash')

    signed_pdf = fields.Binary('Signed PDF', readonly=True, related='pdf_document_id.signed_pdf')
    signed_pdf_filename = fields.Char('Signed PDF Filename', readonly=True,
                                      related='pdf_document_id.signed_pdf_filename')

    def submit_pdf_document(self, **kwargs):
        if self.pdf_sign_server != 'local':
            return super(ApprovalInstance, self).submit_pdf_document(**kwargs)
        config_pdf_document = dict(kwargs)
        config = self.approval_document_id.get_config_pdf_document(self)
        config_pdf_document.update(config)
        _logger.info("config_pdf_document %s ", config_pdf_document)
        if isinstance(config_pdf_document, models.Model):
            if config_pdf_document._name == 'pdf.document':
                self.pdf_document_id = config_pdf_document
        elif isinstance(config_pdf_document, dict):
            pdf = self.pdf_document_id.sudo().create_from_approval(**config_pdf_document)
            self.pdf_document_id = pdf.id

        return self.pdf_document_id

    def sign_pdf_document(self, **kwargs):
        if self.pdf_sign_server != 'local':
            return super(ApprovalInstance, self).sign_pdf_document(**kwargs)

        config_pdf_document = dict(kwargs)
        approval_task_line = kwargs.get('approval_task_line')
        user_execution = kwargs.get('user_execution')

        config = self.approval_document_id.get_config_pdf_sign_document(
            self, approval_task_line, user_execution
        )
        config_pdf_document.update(config)
        config_pdf_document.setdefault('auto_sign_ca',True)
        config_pdf_document.setdefault('auto_create_ca_default', True)
        self.pdf_document_id.sign_from_approval(
            **config_pdf_document
        )

    def action_sign_all_pdf(self):
        config_pdf_document = self.approval_template_id.get_config_pdf_document(self)
        _logger.info(" config_pdf_document %s ", config_pdf_document)
        if isinstance(config_pdf_document, models.Model):
            if config_pdf_document._name == 'pdf.document':
                self.pdf_document_id = config_pdf_document
        elif isinstance(config_pdf_document, dict):
            pdf = self.pdf_document_id.sudo().create_from_approval(**config_pdf_document)
            self.pdf_document_id = pdf.id
            # self.pdf_document_id.sudo().action_prepare_signature()
        # if not self.pdf_document_id:
        #     config_pdf_document = self.approval_template_id.get_config_pdf_document(self)
        #     _logger.info(" config_pdf_document %s ",config_pdf_document)
        #     if isinstance(config_pdf_document,models.Model):
        #         if config_pdf_document._name == 'pdf.document':
        #             self.pdf_document_id = config_pdf_document
        #     elif isinstance(config_pdf_document,dict):
        #         pdf = self.env['ensure.create.mixin'].ensure_create_dict('pdf.document',config_pdf_document)
        #         self.pdf_document_id = pdf.id
        # if self.pdf_document_id:
        #     self.pdf_document_id.sudo().action_sign_all_pdf()
        #     record = self.pdf_document_id.with_context(bin_size=False)
        #     attachment = self.env['ir.attachment'].create({
        #         'name': 'signed_%s' % record.signed_pdf_filename,
        #         'datas': record.signed_pdf,
        #         'mimetype': 'application/pdf',
        #         'res_model': self.transaction_model_name,
        #         'res_id': self.transaction_id,
        #     })
        #     _logger.info("data sig %s", record.signed_pdf)
