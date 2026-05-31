# -*- coding: utf-8 -*-

from odoo import models, api, tools
import logging

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def send_odoobot_message(self, message):
        """Kirim pesan lewat OdooBot ke user ini"""
        self.ensure_one()
        user_root = self.env.ref('base.user_root')
        MailChannel = self.env['mail.channel'].with_user(user_root)
        channel_info = MailChannel.channel_get([self.id])
        channel = MailChannel.browse(channel_info['id'])
        result = channel.message_post(
            body=message,
            author_id=user_root.partner_id.id,
            message_type="comment",
            subtype="mail.mt_comment"
        )
        return result
