# -*- coding: utf-8 -*-

import logging
import json
import werkzeug

from datetime import datetime, date
from odoo import api, http, SUPERUSER_ID, _, registry as registry_get
from odoo.fields import Datetime, Date, Many2many, One2many
from odoo.exceptions import AccessError
from odoo.http import request

_logger = logging.getLogger(__name__)


class ApprovalAttachmentController(http.Controller):

    @http.route(
        "/approval/attachment/reference/<int:reference_id>/view",
        type="http",
        auth="user",
        methods=["GET"],
    )
    def view_attachment(self, reference_id, **kwargs):
        reference = request.env[
            "approval.attachment.reference"
        ].browse(reference_id).exists()

        if not reference:
            raise AccessError(
                "Attachment reference not found."
            )

        # SECURITY CHECK
        reference.check_access(
            operation="view"
        )

        attachment = reference.attachment_id.sudo()

        return request.make_response(
            attachment.raw,
            headers=[
                (
                    "Content-Type",
                    attachment.mimetype or
                    "application/octet-stream",
                ),
                (
                    "Content-Disposition",
                    'inline; filename="%s"' %
                    attachment.name,
                ),
            ],
        )

    @http.route(
        "/approval/attachment/reference/<int:reference_id>/download",
        type="http",
        auth="user",
        methods=["GET"],
    )
    def download_attachment(self, reference_id, **kwargs):

        reference = request.env[
            "approval.attachment.reference"
        ].browse(reference_id).exists()

        if not reference:
            raise AccessError(
                "Attachment reference not found."
            )

        # SECURITY CHECK
        reference.check_access(operation="download")

        attachment = reference.attachment_id.sudo()

        return request.make_response(
            attachment.raw,
            headers=[
                (
                    "Content-Type",
                    attachment.mimetype or
                    "application/octet-stream",
                ),
                (
                    "Content-Disposition",
                    'attachment; filename="%s"' %
                    attachment.name,
                ),
            ],
        )
