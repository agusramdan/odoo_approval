# -*- coding: utf-8 -*-

import io
import logging
import base64

from io import BytesIO
from PyPDF2 import PdfFileReader, PdfFileWriter

from odoo import _, api, fields, models
from odoo.exceptions import UserError, AccessError
from odoo.tools import datetime

from ..tools.utils import have_method, safe_call_method

from PIL import Image, ImageChops

from odoo import models, fields, api, _, registry, SUPERUSER_ID
from odoo.exceptions import Warning, ValidationError, UserError
from datetime import datetime
from odoo.tools.misc import clean_context, split_every
import tempfile
import os
from pdfrw import PdfReader, PdfWriter
from pdfrw.buildxobj import pagexobj
from pdfrw.toreportlab import makerl
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import A4
import requests
import json
import threading
import qrcode
from io import BytesIO
import base64
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
        # if attachments:
        #     # 2. Create writer SEKALI saja
        #     writer = PdfFileWriter()
        #     # 3. Add generated report
        #     report_reader = PdfFileReader(BytesIO(pdf_content))
        #     for page in report_reader.pages:
        #         writer.addPage(page)
        #
        #     # 4. Add PDF attachments
        #     att_index = 0
        #     for attachment in attachments:
        #         att_index += 1
        #         attachment_content = self.wrap_attachment_header(attachment, att_index)
        #         # attachment_content = base64.b64decode(attachment.datas)
        #         if not attachment_content:
        #             _logger.warning("Skip attachment_content pdf")
        #             continue
        #
        #         attachment_reader = PdfFileReader(BytesIO(attachment_content))
        #
        #         for page in attachment_reader.pages:
        #             writer.addPage(page)
        #
        #     # 5. Generate merged PDF
        #     output = BytesIO()
        #     writer.write(output)
        #     merged_pdf = output.getvalue()
        # else:
        #     merged_pdf = pdf_content

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
        # self.ensure_one()

        # 1. Generate report Odoo
        # report = self.env.ref(xml_id)
        # pdf_content, _ = report.render_qweb_pdf(self.transaction_id)

        # if self:
        #     # 2. Create writer SEKALI saja
        #     writer = PdfFileWriter()
        #     # 3. Add generated report
        #     report_reader = PdfFileReader(BytesIO(pdf_content))
        #     for page in report_reader.pages:
        #         writer.addPage(page)
        #
        #     # 4. Add PDF attachments
        #     att_index = 0
        #     for aar in self:
        #         att_index += 1
        #         if not aar.merge_able:
        #             _logger.warning("no attachment %s ", aar.id)
        #             continue
        #         # attachment = aar.sudo().attachment_id
        #         # if not attachment:
        #         #     _logger.warning("no attachment")
        #         #     continue
        #         # if attachment.mimetype != "application/pdf":
        #         #     _logger.warning("Skip not pdf")
        #         #     continue
        #         # if not attachment.datas:
        #         #     _logger.warning("no data")
        #         #     continue
        #         attachment_content = aar.sudo().wrap_with_attachment_header(att_index)
        #         # attachment_content = base64.b64decode(attachment.datas)
        #         if not attachment_content:
        #             _logger.warning("Skip attachment_content pdf")
        #             continue
        #
        #         attachment_reader = PdfFileReader(BytesIO(attachment_content))
        #
        #         for page in attachment_reader.pages:
        #             writer.addPage(page)
        #
        #     # 5. Generate merged PDF
        #     output = BytesIO()
        #     writer.write(output)
        #     merged_pdf = output.getvalue()
        # else:
        #     merged_pdf = pdf_content
        #
        # return merged_pdf
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

    # def wrap_with_attachment_header(self, att_index, label=None, qr_code=None,
    #                                 gradien_rgb_left=(0xb7 / 255.0, 0x7a / 255.0, 0xa2 / 255.0),
    #                                 gradien_rgb_right=(0x7e / 255.0, 0x45 / 255.0, 0x68 / 255.0)
    #                                 ):
    #     return self.wrap_attachment_header(self.attachment_id, att_index, label, qr_code, gradien_rgb_left,
    #                                        gradien_rgb_right)
    #
    # # gradien_rgb_left=(0x1e / 255.0, 0x3a / 255.0, 0x5f / 255.0),
    # # gradien_rgb_right=(0x1e / 255.0, 0x3a / 255.0, 0x5f / 255.0)
    # # B77AA2 muda
    # # 90577D asli erp
    # # 7E456B
    # def wrap_attachment_header(
    #         self, attachment, att_index, label=None, qr_code=None,
    #         gradien_rgb_left=(0xb7 / 255.0, 0x7a / 255.0, 0xa2 / 255.0),
    #         gradien_rgb_right=(0x7e / 255.0, 0x45 / 255.0, 0x68 / 255.0)
    # ):
    #     if not attachment.datas or attachment.mimetype not in MERGEABLE_MIMETYPES:
    #         return None
    #     is_pdf = attachment.mimetype == 'application/pdf'
    #     content_binary = base64.b64decode(self.attachment_id.datas)
    #     page_w, page_h = A4
    #     header_h = 65.0
    #     content_h = page_h - header_h
    #     margin = 15.0
    #     output = BytesIO()
    #     c = rl_canvas.Canvas(output, pagesize=A4)
    #     ref_code = '%s-ATT-%d' % (self.name or self.attachment_name, att_index)
    #     qr_img = None
    #     if qr_code:
    #         qr_img = ImageReader(BytesIO(base64.b64decode(qr_code)))
    #
    #     qr_size_h = header_h - 10
    #     qr_x = page_w - qr_size_h - 8
    #     qr_y = page_h - header_h + 5
    #
    #     def draw_header():
    #         # Gradient: light blue (left) → navy (right)
    #         navy_r, navy_g, navy_b = gradien_rgb_right
    #         light_r, light_g, light_b = gradien_rgb_left
    #         steps = 100
    #         slice_w = page_w / steps
    #         for i in range(steps):
    #             ratio = i / float(steps)
    #             r = light_r + (navy_r - light_r) * ratio
    #             g = light_g + (navy_g - light_g) * ratio
    #             b = light_b + (navy_b - light_b) * ratio
    #             c.setFillColorRGB(r, g, b)
    #             c.rect(i * slice_w, page_h - header_h, slice_w + 0.5, header_h, fill=1, stroke=0)
    #         badge_size = 32.0
    #         bx = 10.0
    #         by = page_h - header_h + (header_h - badge_size) / 2
    #         c.setFillColorRGB(1, 1, 1)
    #         c.roundRect(bx, by, badge_size, badge_size, 5, fill=1, stroke=0)
    #         c.setFillColorRGB(navy_r, navy_g, navy_b)
    #         c.setFont('Helvetica-Bold', 14)
    #         c.drawCentredString(bx + badge_size / 2, by + 10, str(att_index))
    #         tx = bx + badge_size + 10
    #         c.setFillColorRGB(1, 1, 1)
    #         c.setFont('Helvetica', 8)
    #         c.drawString(tx, page_h - header_h + header_h * 0.62, 'Official Attachment')
    #         c.setFont('Helvetica-Bold', 13)
    #         c.drawString(tx, page_h - header_h + header_h * 0.28, label or ('Attachment %d' % att_index))
    #         if qr_img:
    #             c.drawImage(qr_img, qr_x, qr_y, width=qr_size_h, height=qr_size_h, preserveAspectRatio=True)
    #         rx = qr_x - 8
    #         c.setFillColorRGB(1, 1, 1)
    #         c.setFont('Helvetica', 7)
    #         c.drawRightString(rx, page_h - header_h + header_h * 0.62, 'Uploaded via ERP')
    #         c.setFont('Helvetica-Bold', 8)
    #         c.drawRightString(rx, page_h - header_h + header_h * 0.28, ref_code)
    #
    #     if is_pdf:
    #         reader = PdfReader(BytesIO(content_binary))
    #         for page in reader.pages:
    #             draw_header()
    #             xobj = pagexobj(page)
    #             rl_form = makerl(c, xobj)
    #             mb = page.MediaBox
    #             orig_w = float(mb[2]) - float(mb[0])
    #             orig_h = float(mb[3]) - float(mb[1])
    #             avail_w = page_w - 2 * margin
    #             avail_h = content_h - 2 * margin
    #             scale = min(avail_w / orig_w, avail_h / orig_h)
    #             draw_w = orig_w * scale
    #             draw_h = orig_h * scale
    #             cx = (page_w - draw_w) / 2
    #             cy = (content_h - draw_h) / 2
    #             c.saveState()
    #             c.translate(cx, cy)
    #             c.scale(scale, scale)
    #             c.doForm(rl_form)
    #             c.restoreState()
    #             c.showPage()
    #     else:
    #         draw_header()
    #         img = ImageReader(BytesIO(content_binary))
    #         img_w, img_h = img.getSize()
    #         avail_w = page_w - 2 * margin
    #         avail_h = content_h - 2 * margin
    #         scale = min(avail_w / img_w, avail_h / img_h)
    #         draw_w = img_w * scale
    #         draw_h = img_h * scale
    #         cx = (page_w - draw_w) / 2
    #         cy = (content_h - draw_h) / 2
    #         c.setFillColorRGB(1, 1, 1)
    #         c.rect(0, 0, page_w, content_h, fill=1, stroke=0)
    #         c.drawImage(img, cx, cy, width=draw_w, height=draw_h)
    #         c.showPage()
    #
    #     c.save()
    #     return output.getvalue()
