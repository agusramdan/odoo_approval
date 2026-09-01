# wizard/report_composer_wizard.py

import base64

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ReportComposerWizard(models.TransientModel):
    _name = 'report.composer.wizard'
    _description = 'Report Composer'

    view_id = fields.Integer()
    res_model = fields.Char(
        string='Resource Model',
        required=True,
        readonly=True,
    )

    res_id = fields.Integer(
        string='Resource ID',
        required=True,
        readonly=True,
    )
    report_id = fields.Many2one(
        'ir.actions.report',
        string='Report',
        domain="[('model', '=', res_model)]",
    )

    report_position = fields.Selection(
        [
            ('first', 'First'),
            ('last', 'Last'),
        ],
        string='Report Position',
        default='first',
        required=True,
    )

    line_ids = fields.One2many(
        'report.composer.wizard.line',
        'wizard_id',
        string='Documents',
    )

    selected_count = fields.Integer(
        string='Selected',
        compute='_compute_selected_count',
    )

    result_attachment_id = fields.Many2one(
        'ir.attachment',
        string='Result',
        readonly=True,
    )

    @api.depends('line_ids.selected')
    def _compute_selected_count(self):
        for wizard in self:
            wizard.selected_count = len(
                wizard.line_ids.filtered('selected')
            )

    # ---------------------------------------------------------
    # SOURCE RECORD
    # ---------------------------------------------------------

    def _get_source_record(self):
        self.ensure_one()

        if not self.res_model or not self.res_id:
            raise UserError(
                _('Resource is not defined.')
            )

        record = self.env[
            self.res_model
        ].browse(self.res_id)

        if not record.exists():
            raise UserError(
                _('Source record no longer exists.')
            )

        return record

    def _get_selected_lines(self):
        self.ensure_one()

        lines = self.line_ids.filtered(
            'selected'
        ).sorted(
            key=lambda line: (
                line.sequence,
                line.id,
            )
        )

        if not lines:
            raise UserError(
                _('Please select at least one document.')
            )

        return lines

    # ---------------------------------------------------------
    # REPORT
    # ---------------------------------------------------------

    def _render_report(self, report):
        self.ensure_one()
        record = self._get_source_record()
        pdf_content, content_type = (report.render_qweb_pdf(record.ids))

        return pdf_content

    # ---------------------------------------------------------
    # BUILD
    # ---------------------------------------------------------

    def _build_pdf(self):
        pdf_utils = self.env['report.attachment.line.mixin']
        lines = self.line_ids.filtered('selected').sorted(
            key=lambda line: (line.sequence, line.id,)
        )

        documents = []

        # ---------------------------------------------------------
        # REPORT
        # ---------------------------------------------------------

        if self.report_id:
            report_pdf = self._render_report(self.report_id)
            if self.report_position == 'first':
                documents.insert(0, {
                    'sequence': 0,
                    'name': self.report_id.name,
                    'content': report_pdf,
                })

            else:
                documents.append({
                    'sequence': 999999,
                    'name': self.report_id.name,
                    'content': report_pdf,
                })

        # ---------------------------------------------------------
        # ATTACHMENTS
        # ---------------------------------------------------------
        idx = 0
        for line in lines:
            idx += 1
            pdf_content = pdf_utils.wrap_attachment_with_header(line.attachment_id, idx,header_h=35.0, margin=5.0)
            documents.append({
                'sequence': line.sequence,
                'name': line.name,
                'content': pdf_content,
            })

        # ---------------------------------------------------------
        # SORT
        # ---------------------------------------------------------
        documents.sort(key=lambda document: document['sequence'])
        return pdf_utils.merge_pdfs(documents)

    # ---------------------------------------------------------
    # RESULT
    # ---------------------------------------------------------

    def _get_result_filename(self):
        self.ensure_one()
        record = self._get_source_record()
        name = record.display_name or 'report'
        name = name.replace('/', '_')
        return '%s.pdf' % name

    def _create_result_attachment(self, pdf_content):
        self.ensure_one()
        res_model = None
        res_id = None
        if self.report_id.attachment_use:
            res_model = self.res_model
            res_id = self.res_id
        filename = self._get_result_filename()
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'datas': base64.b64encode(pdf_content),
            'res_model': res_model,
            'res_id': res_id,
            'type': 'binary',
            'mimetype': 'application/pdf',
        })

        self.result_attachment_id = attachment.id
        record = self._get_source_record()
        if hasattr(record, '_report_composer_after_create'):
            return record._report_composer_after_create(attachment)
        else:
            return attachment

    # ---------------------------------------------------------
    # ACTION
    # ---------------------------------------------------------
    def action_select_all(self):
        self.ensure_one()
        self.line_ids.write({"selected": True})
        # "view_id": self.env.ref(
        #     "your_module.view_attachment_select_wizard_form"
        # ).id,
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "view_id": self.view_id if self.view_id else None,
            "target": "new",
        }

    def action_unselect_all(self):
        self.ensure_one()
        self.line_ids.write({"selected": False})
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "view_id":  self.view_id if self.view_id else None,
            "target": "new",
        }

    def action_generate(self):
        self.ensure_one()
        pdf_content = self._build_pdf()
        attachment = self._create_result_attachment(pdf_content)
        return {
            'type': 'ir.actions.act_url',
            'url': (
                    '/web/content/%s?download=true'
                    % attachment.id
            ),
            'target': 'self',
        }

    def action_cancel(self):
        return {
            'type': 'ir.actions.act_window_close',
        }

    def prepare_action_report_composer(self, res_model, res_id, attachments, report=None, view=None):
        lines = []
        sequence = 10
        for attachment in attachments:
            if not attachment.mimetype:
                continue
            if (
                    attachment.mimetype != 'application/pdf'
                    and not attachment.mimetype.startswith('image/')
            ):
                continue

            lines.append((0, 0, {
                'sequence': sequence,
                'attachment_id': attachment.id,
                'selected': False,
            }))

            sequence += 10
        view_id = int(view) if view else None
        wizard = self.create([{
            'res_model': res_model,
            'res_id': res_id,
            'line_ids': lines,
            'view_id': view_id,
            'report_id': report.id if report else None,
        }])[0]

        return {
            'type': 'ir.actions.act_window',
            'name': 'Report Composer',
            'res_model': 'report.composer.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'view_id': view_id,
            'target': 'new',
        }


class ReportComposerWizardLine(models.TransientModel):
    _name = 'report.composer.wizard.line'
    _inherit = ['report.attachment.line.mixin']
    _description = 'Report Composer Attachment Line'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'report.composer.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
        index=True,
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10,
        required=True,
    )

    selected = fields.Boolean(
        string='Select',
        default=True,
    )
