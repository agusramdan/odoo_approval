# -*- coding: utf-8 -*-

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class ApprovalTask(models.Model):
    _inherit = "approval.task"

    def send_notification(self, **kwargs):
        self.ensure_one()
        users = self.get_users_for_notification(**kwargs)
        kwargs['users'] = users
        payload = {
            "event": "approval.task.changed",
            "task_id": self.id,
        }
        bus = self.env["bus.bus"]
        for user in users:
            bus.sendone(
                f"approval.refresh.task.user.{user.id}",
                payload,
            )

        super(ApprovalTask, self).send_notification(**kwargs)
