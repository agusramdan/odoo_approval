# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class ApprovalTask(models.Model):
    _inherit = 'approval.task'

    def approval_done(self, **kwargs):
        records = self
        if not self:
            transaction_id = kwargs.get('transaction_id')
            transaction_model_name = kwargs.get('transaction_model_name')
            if transaction_id and transaction_id:
                records = self.search([
                    ('transaction_id', '=', transaction_id),
                    ('transaction_model_name', '=', transaction_model_name),
                ])

        for approval_task in records:
            self.env["mobile.approval.client"].create_request(
                name=approval_task.name or approval_task.description or approval_task.display_name,
                request_type='unregister_approval',
                transaction_model_name=approval_task.transaction_model_name,
                transaction_id=approval_task.transaction_id,
                approval_task_line_model_name=approval_task.approval_model,
                approval_task_line_id=approval_task.approval_res_id,
             )

        return super(ApprovalTask,records).approval_done(**kwargs)

    def approval_setup(self, transaction_id, transaction_model_name, **kwargs):
        approval_task = self.search([
            ('transaction_id', '=', transaction_id),
            ('transaction_model_name', '=', transaction_model_name),
        ], limit=1)
        users = self.env['res.users'].browse()
        if approval_task:
            users = approval_task.get_users_for_mobile_approval(**kwargs)
        approval_task = super(ApprovalTask,self).approval_setup(transaction_id, transaction_model_name, **kwargs)
        user_unregisters = users - approval_task.get_users_for_mobile_approval(**kwargs)
        if user_unregisters:
            self.env["mobile.approval.client"].create_request(
                name=approval_task.name or approval_task.description or approval_task.display_name,
                number=approval_task.name or approval_task.transaction_display_name,
                document=approval_task.document,
                originator_name=approval_task.requester_id.name,
                url=approval_task.url,
                request_type='unregister_user_approval',
                transaction_model_name=approval_task.transaction_model_name,
                transaction_id=approval_task.transaction_id,
                approval_task_line_model_name=approval_task.approval_model,
                approval_task_line_id=approval_task.approval_res_id,
                user_ids=user_unregisters
            )
        approval_task.send_to_mobile_approval()
        return approval_task

    def send_to_mobile_approval(self):
        for approval_task in self:
            users_for_mobile_approval = approval_task.get_users_for_mobile_approval()
            if users_for_mobile_approval:
                # 'approval_name', 'approval_document', 'approval_task_line_model_name', 'approval_task_line_id', 'url'
                result = self.env["mobile.approval.client"].create_request(
                    name=approval_task.name or approval_task.transaction_display_name or approval_task.display_name,
                    number=approval_task.name or approval_task.transaction_display_name or approval_task.display_name,
                    document=approval_task.document,
                    originator_name=approval_task.requester_id.name,
                    url=approval_task.url,
                    request_type='register_approval',
                    transaction_model_name=approval_task.transaction_model_name,
                    transaction_id=approval_task.transaction_id,
                    approval_task_line_model_name=approval_task.approval_model,
                    approval_task_line_id=approval_task.approval_res_id,
                    user_ids=users_for_mobile_approval
                )
                result.dispatch_send()
