# -*- coding: utf-8 -*-

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ApprovalSelectionMixin(models.AbstractModel):
    _name = "approval.selection.mixin"
    _description = "Approval Selection Mixin"

    def _get_selection_label(self, field_name, value=None):
        self.ensure_one()
        field = self._fields[field_name]
        if value is None:
            value = self[field_name]
        selection = field.selection

        if callable(selection):
            selection = selection(self.env)

        return dict(selection).get(value)

    def _get_selection_dict(self, field_name):
        task = self.ensure_one()
        status_approval = getattr(task, field_name, None) if hasattr(task, field_name) else None
        state_label = self._get_selection_label(field_name, value=status_approval)
        return {
            "key": status_approval,
            "label": state_label,
        }


class ApprovalReportLineMixin(models.AbstractModel):
    _name = "approval.report.line.mixin"
    _inherit = ["approval.selection.mixin"]
    _description = "Approval Report Mixin"

    def get_approval_report_visuals(self, user=None):
        visuals = []
        if user:
            signature_image = user.sudo().get_signature_visual()
            if signature_image:
                visuals.append(signature_image)
        # if self.verification_qr:
        #     visuals.append({
        #         "type": "qr",
        #         "image": self.verification_qr,
        #         "alt": "Verification QR",
        #         "style": (
        #             "height: 60px;"
        #             "width: 60px;"
        #         ),
        #     })
        return visuals

    def create_approval_report_line_data_default(self, user=None, label=None, date_execution=None, state=None):
        date_str = None
        if date_execution:
            date_str = fields.Datetime.context_timestamp(self, date_execution).strftime('%d/%m/%Y %H:%M')
        result = {
            "obj": self,
            "user": {
                "obj": user,
                "name": user.name if user else None,
            },
            "label": label,
            "date": {
                "obj": date_execution,
                "date_str": date_str,
            },
            "state": state,
            "visuals": self.get_approval_report_visuals(user),
        }
        return result

    def get_approval_report_line_data(
            self,
            field_name_status="status_approval",
            field_name_user_execution="user_execution_id",
            field_name_sign_title="sign_title",
            field_name_date_execution="date_execution"
    ):
        task = self.ensure_one()
        label = getattr(task, field_name_sign_title, None) if hasattr(task, field_name_sign_title) else ""
        if not label and task:
            label = task.display_name if hasattr(task, 'display_name') else task.name if hasattr(task, 'name') else ""
        if hasattr(task, field_name_user_execution):
            user_execution = getattr(task, field_name_user_execution, None)
        else:
            user_execution = None

        if hasattr(task, field_name_sign_title):
            date_execution = getattr(task, field_name_date_execution, None)
        else:
            date_execution = None

        return task.create_approval_report_line_data_default(
            user=user_execution, label=label,
            date_execution=date_execution,
            state=self._get_selection_dict(field_name=field_name_status)
        )

    def get_approval_report_lines(self):
        kw = {}
        approval_template_line = self.env['approval.template.line'].search_template_line_by_model(self._name)
        if approval_template_line:
            kw = {
                "field_name_status": approval_template_line.state_field or 'status_approval',
                "field_name_user_execution": approval_template_line.field_user_execution_id or 'user_execution_id',
                "field_name_sign_title": approval_template_line.field_sign_title or 'display_name',
                "field_name_date_execution": approval_template_line.field_date_execution or "date_execution"
            }
        return [task.get_approval_report_line_data(**kw) for task in self]


class ApprovalReportMixin(models.AbstractModel):
    _name = "approval.report.mixin"
    _description = "Approval Report Mixin"

    def get_approval_report_data(self):
        self.ensure_one()
        approval_document = self.env['approval.document'].get_approval_document(self)
        approval_template = self.env['approval.template'].search_template(
            transaction=self, transaction_model_name=self._name
        )
        kw = {
            "approval_document": approval_document,
            "approval_template": approval_template,
        }
        return {
            "enabled": self.approval_report_enabled(**kw),
            "state": self.get_approval_report_state(**kw),
            "lines": self.get_approval_report_lines(**kw),
            "history": self.get_approval_report_history(),
            "verification": self.get_approval_report_verification(),
        }

    def approval_report_enabled(self, approval_document=None, approval_template=None, **kwargs):
        return bool(self.get_approval_report_lines())

    def get_approval_report_state(self, approval_document=None, approval_template=None, **kwargs):
        return {
            "key": False,
            "label": False,
        }

    def get_approval_report_lines(self, approval_document=None, approval_template=None, **kwargs):
        self.ensure_one()
        return self.approval_task_line.get_approval_report_lines()

    def get_approval_report_history(self):
        return []

    def get_approval_report_verification(self):
        return {
            "enabled": False,
            "visuals": [],
        }
