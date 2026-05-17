# -*- coding: utf-8 -*-

from odoo import models, api, tools
import logging

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

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

    def has_group_id(self, group_id):
        uid = self.id
        if uid and uid != self._uid:
            self = self.with_user(uid)

        return self._has_group_id(group_id)

    def get_users_for_notification(self, company=None):
        if not self:
            return
        if self.env.context.get("__user_with_delegatee_notification"):
            return self
        if company:
            result = self.browse()
            for user in self:
                if company.id in user.company_ids.ids:
                    result |= user
        else:
            result = self
        result = result.get_notification_users(company_id=company)
        return result.with_context(__user_with_delegatee_notification=True)

    def get_users_for_approval(self, company=None):
        if not self:
            return self
        if self.env.context.get("__user_with_delegator_approval"):
            return self
        if company:
            result = self.browse()
            for user in self:
                if company.id in user.company_ids.ids:
                    result |= user
            result |= self
        else:
            result = self
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

        return self.env['user.delegation'].get_notification_user_ids(user_ids=[self._uid], company_id=company_id)

    def send_odoobot_message(self, message):
        """Kirim pesan lewat OdooBot ke user ini"""
        self.ensure_one()
        user_root = self.env.ref('base.user_root')
        MailChannel = self.env['mail.channel'].with_user(user_root)
        channel_info = MailChannel.channel_get([self.partner_id.id])
        channel = MailChannel.browse(channel_info['id'])
        result = channel.message_post(
            body=message,
            author_id=user_root.partner_id.id,
            message_type="comment",
            subtype="mail.mt_comment"
        )
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
