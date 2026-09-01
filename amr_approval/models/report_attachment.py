# models/report_composer_mixin.py

import io
from odoo.exceptions import UserError
from pdfrw import PdfReader
from pdfrw.buildxobj import pagexobj
from pdfrw.toreportlab import makerl
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import A4
from io import BytesIO
import base64
from odoo import _, api, fields, models

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


class ReportAttachmentLineMixin(models.AbstractModel):
    _name = 'report.attachment.line.mixin'
    _description = 'Report Composer Attachment Line'

    attachment_id = fields.Many2one(
        'ir.attachment',
        string='Attachment',
        readonly=True,
        ondelete='cascade',
    )

    name = fields.Char(
        related='attachment_id.name',
        string='File Name',
        readonly=True,
    )

    mimetype = fields.Char(
        related='attachment_id.mimetype',
        string='Mimetype',
        readonly=True,
    )

    file_size = fields.Integer(
        related='attachment_id.file_size',
        string='Size',
        readonly=True,
    )

    file_type = fields.Selection(
        [
            ('pdf', 'PDF'),
            ('image', 'Image'),
            ('other', 'Other'),
        ],
        string='Type',
        compute='_compute_file_type',
    )

    @api.depends('mimetype')
    def _compute_file_type(self):
        for line in self:
            mimetype = line.mimetype or ''

            if mimetype == 'application/pdf':
                line.file_type = 'pdf'

            elif mimetype.startswith('image/'):
                line.file_type = 'image'

            else:
                line.file_type = 'other'

    @api.model
    def merge_pdfs(self, documents):
        try:
            from PyPDF2 import PdfFileReader, PdfFileWriter
        except ImportError:
            raise UserError(_('PyPDF2 is required.'))

        if not documents:
            raise UserError(_('No documents to merge.'))

        writer = PdfFileWriter()

        try:
            for document in documents:
                pdf_file = io.BytesIO(document['content'])
                reader = PdfFileReader(pdf_file)
                for page_number in range(reader.getNumPages()):
                    writer.addPage(reader.getPage(page_number))

            output = io.BytesIO()
            writer.write(output)

            return output.getvalue()

        except Exception as error:
            raise UserError(
                _('Unable to merge documents.\n\n%s') % error
            )

    @api.model
    def wrap_attachment_with_header(
            self, attachment, att_index=1, label=None, qr_code=None,
            gradien_rgb_left=(0xb7 / 255.0, 0x7a / 255.0, 0xa2 / 255.0),
            gradien_rgb_right=(0x7e / 255.0, 0x45 / 255.0, 0x68 / 255.0),
            header_h=65.0,
            margin=15.0
    ):
        """Bungkus konten (PDF/gambar) dengan header navy 'Official Attachment' di atas halaman A4."""

        if not attachment.datas or attachment.mimetype not in MERGEABLE_MIMETYPES:
            return None
        is_pdf = attachment.mimetype == 'application/pdf'
        content_binary = base64.b64decode(attachment.datas)
        page_w, page_h = A4
        content_h = page_h - header_h
        output = BytesIO()
        c = rl_canvas.Canvas(output, pagesize=A4)
        ref_code = '%s-ATT-%d' % (attachment.name, att_index)
        qr_img = None
        if qr_code:
            qr_img = ImageReader(BytesIO(base64.b64decode(qr_code)))

        qr_size_h = header_h - 10
        qr_x = page_w - qr_size_h - 8
        qr_y = page_h - header_h + 5

        def draw_header():
            # Gradient: light blue (left) → navy (right)
            navy_r, navy_g, navy_b = gradien_rgb_right
            light_r, light_g, light_b = gradien_rgb_left
            steps = 100
            slice_w = page_w / steps
            for i in range(steps):
                ratio = i / float(steps)
                r = light_r + (navy_r - light_r) * ratio
                g = light_g + (navy_g - light_g) * ratio
                b = light_b + (navy_b - light_b) * ratio
                c.setFillColorRGB(r, g, b)
                c.rect(i * slice_w, page_h - header_h, slice_w + 0.5, header_h, fill=1, stroke=0)
            badge_size = 32.0
            bx = 10.0
            by = page_h - header_h + (header_h - badge_size) / 2
            c.setFillColorRGB(1, 1, 1)
            c.roundRect(bx, by, badge_size, badge_size, 5, fill=1, stroke=0)
            c.setFillColorRGB(navy_r, navy_g, navy_b)
            c.setFont('Helvetica-Bold', 14)
            c.drawCentredString(bx + badge_size / 2, by + 10, str(att_index))
            tx = bx + badge_size + 10
            c.setFillColorRGB(1, 1, 1)
            c.setFont('Helvetica', 8)
            c.drawString(tx, page_h - header_h + header_h * 0.62, 'Official Attachment')
            c.setFont('Helvetica-Bold', 13)
            c.drawString(tx, page_h - header_h + header_h * 0.28, label or ('Attachment %d' % att_index))
            if qr_img:
                c.drawImage(qr_img, qr_x, qr_y, width=qr_size_h, height=qr_size_h, preserveAspectRatio=True)
            rx = qr_x - 8
            c.setFillColorRGB(1, 1, 1)
            c.setFont('Helvetica', 7)
            c.drawRightString(rx, page_h - header_h + header_h * 0.62, 'Uploaded via ERP')
            c.setFont('Helvetica-Bold', 8)
            c.drawRightString(rx, page_h - header_h + header_h * 0.28, ref_code)

        if is_pdf:
            reader = PdfReader(BytesIO(content_binary))
            for page in reader.pages:
                draw_header()
                xobj = pagexobj(page)
                rl_form = makerl(c, xobj)
                mb = page.MediaBox
                orig_w = float(mb[2]) - float(mb[0])
                orig_h = float(mb[3]) - float(mb[1])
                avail_w = page_w - 2 * margin
                avail_h = content_h - 2 * margin
                scale = min(avail_w / orig_w, avail_h / orig_h)
                draw_w = orig_w * scale
                draw_h = orig_h * scale
                cx = (page_w - draw_w) / 2
                cy = (content_h - draw_h) / 2
                c.saveState()
                c.translate(cx, cy)
                c.scale(scale, scale)
                c.doForm(rl_form)
                c.restoreState()
                c.showPage()
        else:
            draw_header()
            img = ImageReader(BytesIO(content_binary))
            img_w, img_h = img.getSize()
            avail_w = page_w - 2 * margin
            avail_h = content_h - 2 * margin
            scale = min(avail_w / img_w, avail_h / img_h)
            draw_w = img_w * scale
            draw_h = img_h * scale
            cx = (page_w - draw_w) / 2
            cy = (content_h - draw_h) / 2
            c.setFillColorRGB(1, 1, 1)
            c.rect(0, 0, page_w, content_h, fill=1, stroke=0)
            c.drawImage(img, cx, cy, width=draw_w, height=draw_h)
            c.showPage()

        c.save()
        return output.getvalue()
