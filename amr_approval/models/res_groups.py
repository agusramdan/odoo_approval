# -*- coding: utf-8 -*-

from odoo import models
import logging

_logger = logging.getLogger(__name__)


class ResGroups(models.Model):
    _inherit = 'res.groups'

    def get_users_for_notification(self, company=None):
        if self:
            return self.users.get_users_for_notification(company=company)
        return self.users.browse()

    def get_users_for_approval(self, company=None):
        if self:
            return self.users.get_users_for_approval(company=company)
        return self.users.browse()

    def prepare_dict_approval_task_line(self, **kwargs):
        if not self:
            return {}
        line_id = self._context.get('approval_matrix_rule_line_id')
        if line_id:
            line = self.env['approval.matrix.rule.line'].browse(line_id)
            res = line.prepare_dict_approval_task_line(**kwargs) or {}
        else:
            res = {}

        if len(self.ids) > 1:
            res.update({
                'type_approval': 'multi_group',
                'group_ids': self.ids,
            })
        else:
            res = {
                'type_approval': 'group',
                'group_id': self.id,
            }
        return res
