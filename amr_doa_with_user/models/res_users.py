# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools

import logging

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def doa_exclude_group_ext_id(self):
        return ['base.group_user', 'base.group_system', 'base.group_erp_manager',
                'amr_approval.group_doa_internal_user_create']

    @tools.ormcache()
    def doa_exclude_groups(self):
        res_groups = self.env['res.groups'].browse()
        for group_name in self.doa_exclude_group_ext_id():
            res_groups |= self.env.ref(group_name)
        return res_groups

    def has_group(self, group_ext_id=None):
        # use singleton's id if called on a non-empty recordset, otherwise
        # context uid
        # addons documents call document
        if not group_ext_id:
            # perlu di chek lebih lanjut dugaan kuat bahwa js dari addons tidak mengirimkan infomasi yang benar
            _logger.warning(
                "User %s has group call without group_ext_id",
                self
            )
            return False

        base_groups_access = super(ResUsers, self).has_group(group_ext_id)
        # Always return True for base.group_user
        if (base_groups_access or
                group_ext_id is None or
                group_ext_id in self.doa_exclude_group_ext_id()):
            return base_groups_access

        base_groups_access = self.has_delegate_group_ext_id(group_ext_id)
        if base_groups_access:
            _logger.info(
                "User %s has group %s through delegation.",
                self.login, group_ext_id
            )
        return base_groups_access

    def has_group_id(self, group_id, with_delegate=True):
        return super(ResUsers, self).has_group_id(group_id) or (with_delegate and self.has_delegate_group_id(group_id))

    def has_delegate_group_id(self, group_id: int):
        """
        Checks this user as delegate/proxy user have DoA form delegator user given group delegator user to delegate/proxy user.
        """
        if group_id:
            uid = self.id
            if uid and uid != self._uid:
                self = self.with_user(uid)
            return self.env['user.delegation'].has_delegate_group(self._uid, group_id)
        else:
            return False

    def get_delegate_user_group(self):
        """
        Get all delegations user group for this proxy user.
        :return: {
            'user_ids': [user_id1, user_id2, ...],
            'group_ids': [group_id1, group_id2, ...]
            'user_delegate_ids': [user_delegate_id1, user_delegate_id2, ...]
            }
        """
        uid = self.id
        if uid and uid != self._uid:
            uid = self._uid
        return self.env['user.delegation'].get_delegations_user_group_for_delegatee(uid)

    def get_notification_users(self, company_id=None):
        if self:
            notification_users_ids = self.env['user.delegation'].get_notification_user_ids(self.ids,
                                                                                           company_id=company_id)
            if notification_users_ids:
                return self.browse(notification_users_ids)
        return self.browse()

    def get_delegation(self, delegator_ids, company_id=None):
        # self is delegatee
        # this function chek before approve
        if self and delegator_ids:
            record = self.ensure_one()
            if record.id not in delegator_ids:
                return self.env['user.delegation'].get_all_delegations(
                    delegatee_id=record.id, delegator_id=delegator_ids, company_id=company_id, limit=1
                )
        return self.env['user.delegation'].browse()

    def get_delegators(self, company_id=None):
        if self:
            delegator_ids = self.env['user.delegation'].get_all_delegator(self.ids, company_id=company_id)
            if delegator_ids:
                return self.browse(delegator_ids)
        return self.browse()

    def get_delegatee(self, company_id=None):
        if self:
            delegatee_ids = self.env['user.delegation'].get_all_delegatee(self.ids, company_id=company_id)
            if delegatee_ids:
                return self.browse(delegatee_ids)
        return self.browse()

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
