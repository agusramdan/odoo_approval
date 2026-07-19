# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class UserCaDataWizard(models.TransientModel):
    _inherit = 'sign.ca.select.wizard'

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        res['user_id'] = self.env.user.id
        if (
                self.env.context.get('active_id')
                and self.env.context.get('active_model') == 'pdf.sign'
        ):
            res['pdf_sign_id'] = self.env.context['active_id']
        if (
                self.env.context.get('approval_task_line_id')
                and self.env.context.get('approval_task_line_model') == 'pdf.sign'
        ):
            res['pdf_sign_id'] = self.env.context['approval_task_line_id']
        res['user_ca_id'] = self.user_ca_id.search([('user_id', '=', self.env.user.id)], limit=1).id
        return res
