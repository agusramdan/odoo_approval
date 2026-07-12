# -*- coding: utf-8 -*-

import base64
import hashlib
import json
import fitz
import logging
from io import BytesIO

from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.fields import enumerate_sig_fields
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers as ph_signers
from pyhanko.sign.signers import PdfSignatureMetadata
from pyhanko.sign.signers.cms_embedder import SigAppearanceSetup
from pyhanko.sign.fields import SigFieldSpec, append_signature_field
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PdfSign(models.Model):
    _name = 'pdf.sign'
    _inherit = [_name, 'approval.line.auto.register.mixin']
