# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, AccessError
from odoo.tools import datetime

from odoo import models, fields, api, _, registry, SUPERUSER_ID
from odoo.exceptions import Warning, ValidationError, UserError
from odoo.tools.misc import clean_context, split_every

from odoo import api, fields, models
from odoo.exceptions import AccessError

import logging

_logger = logging.getLogger(__name__)

MERGEABLE_MIMETYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/bmp",
    "image/webp",
}


class ApprovalAttachmentReference(models.Model):
    _name = "approval.attachment.reference"
    _inherit = 'report.attachment.line.mixin'
    _description = "Approval Attachment Reference"
    _rec_name = "attachment_id"

    approval_instance_id = fields.Many2one(
        "approval.instance",
        string="Approval Instance",
        required=True,
        ondelete="cascade",
        index=True,
    )

    attachment_id = fields.Many2one(
        "ir.attachment",
        string="Attachment",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char()
    attachment_name = fields.Char(
        related="attachment_id.name",
        string="Attachment Name",
        readonly=True,
    )

    mimetype = fields.Char(
        related="attachment_id.mimetype",
        string="MIME Type",
        readonly=True,
    )

    file_size = fields.Integer(
        related="attachment_id.file_size",
        string="File Size",
        readonly=True,
    )

    create_uid = fields.Many2one(
        "res.users",
        string="Created By",
        readonly=True,
    )

    create_date = fields.Datetime(
        string="Created At",
        readonly=True,
    )
    copy_attachment_id = fields.Many2one(
        "ir.attachment",
        string="Copy Attachment",
        ondelete="cascade",
    )

    def ensure_copy_attachment(self):
        for rec in self:
            approval_instance = rec.approval_instance_id
            if not rec.copy_attachment_id and approval_instance:
                rec.copy_attachment_id = rec.attachment_id.sudo().copy({
                    "res_model": approval_instance.transaction_model_name,
                    "res_id": approval_instance.transaction_id,
                    "res_field": False,
                })

    def ensure_copy_attachment_unlink(self):
        for rec in self:
            if rec.copy_attachment_id:
                rec.copy_attachment_id.sudo().unlink()

    _sql_constraints = [
        (
            "approval_instance_attachment_unique",
            "unique(approval_instance_id, attachment_id)",
            "The attachment is already referenced by this approval instance.",
        ),
    ]
    merge_able = fields.Boolean(
        string="Merge Able",
        compute="_compute_merge_able",
        store=True,
        compute_sudo=True
    )

    @api.depends("mimetype", 'attachment_id', 'attachment_id.mimetype')
    def _compute_merge_able(self):
        for record in self:
            attachment = record.attachment_id.sudo()
            record.merge_able = attachment and attachment.datas and attachment.mimetype in MERGEABLE_MIMETYPES

    def check_access(self, operation="view"):
        self.ensure_one()

        instance = self.approval_instance_id

        if not instance:
            raise AccessError("Approval instance not found.")

        # Current approval task
        if not instance.access_requester:
            instance.check_current_task_access()

        if operation not in ("view", "download"):
            raise AccessError("Invalid attachment operation.")

        return True

    def action_view(self):
        self.ensure_one()
        self.check_access("view")
        return {
            "type": "ir.actions.act_url",
            "url": (
                    "/approval/attachment/reference/%s/view"
                    % self.id
            ),
            "target": "new",
        }

    def action_download(self):
        self.ensure_one()
        self.check_access("download")
        return {
            "type": "ir.actions.act_url",
            "url": (
                    "/approval/attachment/reference/%s/download"
                    % self.id
            ),
            "target": "self",
        }

    @api.model
    def merge_pdf_with_attachments(self, pdf_content, attachments):

        pdf_utils = self.env['report.attachment.line.mixin']
        documents = [{
            'sequence': 0,
            'name': self.report_id.name,
            'content': pdf_content,
        }]
        # ---------------------------------------------------------
        # ATTACHMENTS
        # ---------------------------------------------------------
        idx = 0
        for attachment in attachments:
            idx += 1
            pdf_content = pdf_utils.wrap_attachment_with_header(attachment.sudo(), idx)
            documents.append({
                'name': attachment.name,
                'content': pdf_content,
            })
        return pdf_utils.merge_pdfs(documents)

    def merge_pdf_with_attachment(self, pdf_content):

        pdf_utils = self.env['report.attachment.line.mixin']
        documents = [{
            'sequence': 0,
            'name': self.report_id.name,
            'content': pdf_content,
        }]
        # ---------------------------------------------------------
        # ATTACHMENTS
        # ---------------------------------------------------------
        idx = 0
        for line in self:
            if not line.merge_able:
                continue
            idx += 1
            pdf_content = pdf_utils.wrap_attachment_with_header(line.attachment_id.sudo(), idx)
            documents.append({
                'name': line.name,
                'content': pdf_content,
            })
        return pdf_utils.merge_pdfs(documents)
