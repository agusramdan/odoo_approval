# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import AccessError


class ApprovalAttachmentReference(models.Model):
    _name = "approval.attachment.reference"
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
        ondelete="restrict",
        index=True,
    )

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

    _sql_constraints = [
        (
            "approval_instance_attachment_unique",
            "unique(approval_instance_id, attachment_id)",
            "The attachment is already referenced by this approval instance.",
        ),
    ]

    def check_access(self, operation="view"):
        self.ensure_one()

        instance = self.approval_instance_id

        if not instance:
            raise AccessError("Approval instance not found.")

        # Current approval task
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
