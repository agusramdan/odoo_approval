# -*- coding: utf-8 -*-

import traceback
import io
import logging
import base64

# from io import BytesIO
from PIL import Image, ImageChops

from odoo import _, api, fields, models, tools

_logger = logging.getLogger(__name__)

# Bounds used to strip the paper background off a scanned signature. The paper level is
# detected per image so a cream or grey scan clears as well as a white one, but nothing
# darker than FLOOR may be mistaken for paper. Pixels a full SPAN below the paper level
# are kept opaque and the alpha ramps in between, so anti-aliased strokes stay smooth.
SIGNATURE_PAPER_FLOOR = 170
SIGNATURE_INK_SPAN = 75


class ResUsers(models.Model):
    _inherit = 'res.users'

    signature_image = fields.Binary(
        string='Signature',
        attachment=True,
    )
    signature_image_filename = fields.Char(
        string='Signature Filename',
    )

    def _get_signature_attachment(self, field_name='signature_image'):
        self.ensure_one()
        return self.env['ir.attachment'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('res_field', '=', field_name),
        ], limit=1)

    def get_signature_style(self, signature, mimetype='image/*', width=90, height=80):
        """Inline CSS for a signature box. Drawn as a background-image so
        background-size: contain scales it to fit either way; object-fit would
        read better but the PDF engine may not support it."""
        style = ('height: %spx; width: %spx; border: 1px solid black;'
                 ' margin: 10px auto 4px auto;' % (height, width))
        if signature:
            signature = self._clear_signature_background(signature)
            if isinstance(signature, bytes):
                signature = signature.decode()
            style += (" background-image: url('data:%s;base64,%s');"
                      " background-size: contain; background-repeat: no-repeat;"
                      " background-position: center;" % (mimetype, signature))
        return style

    def get_signature_visual(self, field_name='signature_image', width=90, height=80):
        result = {'type': 'signature', 'alt': 'Electronic Signature'}
        if self:
            self.ensure_one()
            signature_image = getattr(self, field_name, None)
        else:
            signature_image = None
        if signature_image:
            attachment = self._get_signature_attachment(field_name=field_name)
            mimetype = (
                attachment.mimetype
                if attachment and attachment.mimetype
                else 'image/*'
            )
            signature_image = self._clear_signature_background(signature_image)
        else:
            mimetype = 'image/*'

        if signature_image:
            result.update({
                'image': signature_image,
                'mimetype': mimetype,
                'style': self.get_signature_style(signature_image, mimetype=mimetype, width=width, height=height),
            })
        else:
            _logger.warning("user %s has no signature image to display in report visual.", self.name)
            result['style'] = self.get_signature_style(signature_image, width=width, height=height)
        return result

    def _signature_paper_level(self, grey):
        """Grey level of the paper: the most common bright tone, detected per image
        so a cream or grey scan clears as well as a white one. None if no bright
        tone exists to tell apart from the strokes."""
        histogram = grey.histogram()[SIGNATURE_PAPER_FLOOR:]
        if not any(histogram):
            return None
        return SIGNATURE_PAPER_FLOOR + histogram.index(max(histogram))

    def _clear_signature_background(self, signature):
        """Drop the paper background so a scan prints like a transparent PNG.
        Returns the signature untouched if undecodable, since a bad upload must
        never break the printout."""
        try:
            image = Image.open(io.BytesIO(base64.b64decode(signature))).convert('RGBA')
            grey = image.convert('L')
            paper = self._signature_paper_level(grey)
            if paper is None:
                return signature
            ink = max(paper - SIGNATURE_INK_SPAN, 0)
            span = paper - ink or 1
            alpha = grey.point(lambda level: 255 if level <= ink else (
                0 if level >= paper else int(255 * (paper - level) / span)))
            # Whatever the uploaded PNG already made transparent stays transparent.
            alpha = ImageChops.multiply(image.getchannel('A'), alpha)
            image.putalpha(alpha)
            buffer = io.BytesIO()
            image.save(buffer, 'PNG')
            return base64.b64encode(buffer.getvalue())
        except Exception:
            _logger.warning("Unreadable signature image, printing it as uploaded", exc_info=True)
            return signature

    def get_phone_number(self):
        partner = self.partner_id
        if 'hr.employee' in self.env:
            employees = self.env['hr.employee'].sudo().search([('user_id', '=', self.id)])
            for emp in employees:
                phone_number = partner.format_phone_number(getattr(emp, 'mobile_phone', None))
                if phone_number:
                    return phone_number

        return partner.get_phone_number()

    @api.model
    @tools.ormcache('self._uid', 'group_id')
    def _has_group_id(self, group_id):
        """Checks whether user belongs to given group.
        """
        self._cr.execute("""SELECT 1 FROM res_groups_users_rel as gu
                                INNER JOIN ir_model_data d on gu.gid = d.res_id
                                WHERE uid=%s AND res_id = %s""",
                         (self._uid, group_id))
        return bool(self._cr.fetchone())

    def user_has_any_group(self, groups):
        user = self.env.user
        return any(user.has_group_id(group.id) for group in groups)

    def has_group_id(self, group_id):
        uid = self.id
        if uid and uid != self._uid:
            self = self.with_user(uid)

        return self._has_group_id(group_id)

    def get_users_for_notification(self, company=None):
        if not self:
            return self
        if company:
            result = self.browse()
            for user in self:
                if company.id in user.company_ids.ids:
                    result |= user
        else:
            # _logger.warning(
            #     "get_users_for_notification Without company dipanggil dari:\n%s",
            #     ''.join(traceback.format_stack()),
            # )
            result = self
        if result.env.context.get("__user_with_delegatee_notification"):
            return result
        result = result.get_notification_users(company_id=company)
        return result.with_context(__user_with_delegatee_notification=True)

    def get_users_for_approval(self, company=None):
        if not self:
            return self
        if company:
            result = self.browse()
            for user in self:
                if company.id in user.company_ids.ids:
                    result |= user
        else:
            # _logger.warning(
            #     "get_users_for_approval Without company dipanggil dari:\n%s",
            #     ''.join(traceback.format_stack()),
            # )
            result = self

        if result.env.context.get("__user_with_delegator_approval"):
            return result
        # Tambahkan delegatee user
        result = result | result.get_delegatee(company_id=company)
        return result.with_context(__user_with_delegatee_approval=True)

    def has_delegate_group_ext_id(self, group_ext_id):
        group = self.env.ref(group_ext_id, raise_if_not_found=False)
        return group and self.has_delegate_group_id(group.id)

    @api.model
    def has_delegate_group_id(self, group_id: int):
        """
        metode ini akan di override di modul amr_doa_activate
        """
        return False

    def get_notification_users(self, company_id=None):
        """
        metode ini akan di override di modul amr_doa_activate
        """
        return self

    def get_delegation(self, delegator_ids, company_id=None):
        """
        metode ini akan di override di modul amr_doa_activate
        """
        return self.env['user.delegation'].browse()

    def get_delegatee(self, company_id=None):
        """
        metode ini akan di override di modul amr_doa
        """
        return self.browse()

    def get_delegators(self, company_id=None):
        """
        metode ini akan di override di modul amr_doa_activate
        """
        return self.browse()

    @api.model
    def get_delegate_user_group(self):
        """Get all delegations user group for this proxy user."""
        return {
            'user_ids': [],
            'group_ids': [],
            'user_delegate_ids': []
        }

    def get_notification_user_ids(self, company_id=None):
        """
        Override method to return the user itself as a notification recipient.
        This is useful for cases where the user needs to receive notifications
        about their own actions or changes.
        """

        uid = self.id
        if uid and uid != self._uid:
            self = self.with_user(uid)

        return self.env['user.delegation'].get_notification_user_ids(delegator_ids=[self._uid], company_id=company_id)

    def send_odoobot_message(self, message):
        result = None
        for user in self:
            # user.partner_id.send_odoobot_message(message)
            try:
                with self.env.cr.savepoint():
                    if self._uid == user.id:
                        partner = user.partner_id
                    else:
                        partner = user.partner_id.with_user(user)
                    result = partner.send_odoobot_message(message)
            except Exception:
                _logger.info('User #%i %s error chanel.', user.id, user.name)
        return result

    def prepare_dict_approval_task_line(self, **kwargs):
        if not self:
            return {}
        line = self._context.get('approval_matrix_rule_line')
        if line:
            res = line.prepare_dict_approval_task_line(**kwargs) or {}
        else:
            res = {}
        if len(self.ids) > 1:
            res.update({
                'type_approval': 'multi_user',
                'user_ids': self.ids,
            })
        else:
            res.update({
                'type_approval': 'user',
                'user_id': self.id,
            })

        return res
