# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

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
    pre_signed_pdf = fields.Binary('Pre Signed PDF', readonly=True, related='pdf_document_id.pre_signed_pdf')
    signed_pdf = fields.Binary('Signed PDF', readonly=True, related='pdf_document_id.signed_pdf')
    signed_pdf_filename = fields.Char(
        'Signed PDF Filename', readonly=True, related='pdf_document_id.signed_pdf_filename'
    )

    def submit_pdf_document(self, **kwargs):
        if self.pdf_sign_server != 'local':
            _logger.info("call submit_pdf_document %s", self.pdf_sign_server)
            return super(ApprovalInstance, self).submit_pdf_document(**kwargs)
        _logger.info("call submit_pdf_document local")
        # config_pdf_document = dict(kwargs)
        config = self.approval_document_id.get_config_pdf_document(self) or {}
        # config_pdf_document.update(config)
        _logger.info("config_pdf_document %s ", config)
        if isinstance(config, models.Model):
            if config._name == 'pdf.document':
                self.pdf_document_id = config
        elif isinstance(config, dict):
            pdf = self.pdf_document_id.sudo().create_from_approval(**config)
            self.pdf_document_id = pdf.id

        return self.pdf_document_id

    def sign_pdf_document(self, **kwargs):
        if not self:
            _logger.warning("No instance call sign_pdf_document ")
            return
        if self.pdf_sign_server != 'local':
            return super(ApprovalInstance, self).sign_pdf_document(**kwargs)

        approval_task_line = kwargs.get('approval_task_line')
        user_execution = kwargs.get('user_execution')

        config = self.approval_document_id.get_config_pdf_sign_document(
            self, approval_task_line, user_execution, **kwargs
        ) or {}
        if not isinstance(config, dict):
            raise UserError("Invalid response.")
        config.setdefault('auto_sign_ca', True)
        config.setdefault('auto_create_ca_default', True)
        self.pdf_document_id.sign_from_approval(**config)

    def cancel_pdf_document(self, **kwargs):
        if not self:
            _logger.warning("No instance call cancel_pdf_document ")
            return
        if self.pdf_sign_server != 'local':
            return super(ApprovalInstance, self).sign_pdf_document(**kwargs)
        _logger.info("call sign_pdf_document local")
        self.pdf_document_id.cancel_from_approval()

    def action_show_sign_pdf(self):
        if not self:
            _logger.warning("No instance call sign_pdf_document ")
            return
        if self.pdf_sign_server != 'local':
            _logger.info("call sign_pdf_document %s", self.pdf_sign_server)
            return super(ApprovalInstance, self).action_show_sign_pdf()

        self.ensure_one()
        view = self.env.ref(
            'amr_approval_esign.view_approval_instance_pdf_document_form'
        )

        return {
            'type': 'ir.actions.act_window',
            'name': 'Sign PDF',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': view.id,
            'target': 'new',
        }
