# -*- coding: utf-8 -*-

import logging
import re
from odoo import models, api, tools

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def format_phone_number(self, phone):
        if not phone:
            return False

        phone = re.sub(r'\D', '', phone)
        if phone.startswith('0'):
            phone = '62' + phone[1:]
        elif phone.startswith('62'):
            pass
        elif not phone.startswith('62'):
            phone = '62' + phone
        return phone

    def get_phone_number(self):
        if not self:
            return None
        return (
                self.format_phone_number(self.mobile) or
                self.format_phone_number(self.phone) or
                self.mobile or
                self.phone
        )


    def send_odoobot_message(self, message):
        """Kirim pesan lewat OdooBot ke user ini"""
        self.ensure_one()
        user_root = self.env.ref('base.user_root')
        MailChannel = self.env['mail.channel'].with_user(user_root)
        channel_info = MailChannel.channel_get([user_root.partner_id.id])
        channel = MailChannel.browse(channel_info['id'])
        result = channel.message_post(
            body=message,
            author_id=user_root.partner_id.id,
            message_type="comment",
            subtype="mail.mt_comment"
        )
        return result
