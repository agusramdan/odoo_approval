# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class ApprovalTask(models.Model):
    _inherit = 'approval.task'

    def get_approval_task_client(self, path='/api/v1/approval/aggregator', method="POST"):
        server_auth_id = int(
            self.env['ir.config_parameter']
            .sudo()
            .get_param('approval_server_endpoint', 0)
        )
        service_code = self.env['service.endpoint'].browse(server_auth_id)
        return self.env["service.client"].get_service_client(service_code, path=path, method=method)

    def get_register_approval_task_client(self):
        return self.get_approval_task_client()

    def get_unregister_approval_task_client(self):
        return self.get_approval_task_client()

    def send_to_approval_aggregator(self, **kwargs):
        def user_to_dict(user):
            return {
                'email': user.email,
                'login': user.login,
            }

        source_application = self.env['amr.resource.helper'].get_issuer()
        client = self.get_register_approval_task_client()
        for approval_task in self:
            users_for_approval = approval_task.get_users_for_approval()
            if users_for_approval:
                result = client.prepare_payload(
                    source_number=approval_task.name or approval_task.transaction_display_name or approval_task.display_name,
                    source_document=approval_task.document,
                    source_description=approval_task.description,
                    source_application=source_application,
                    source_requester=user_to_dict(approval_task.requester_id),
                    source_url=approval_task.url,
                    source_model=approval_task.transaction_model_name,
                    source_res_id=approval_task.transaction_id,
                    approval_task_line_model_name=approval_task.approval_model,
                    approval_task_line_id=approval_task.approval_res_id,
                    user_ids=[user_to_dict(user) for user in users_for_approval],
                    request_type='register_approval',
                    request_datetime=approval_task.request_approval_task_date
                )
                result.dispatch_send()

    def done_to_approval_aggregator(self, **kwargs):
        client = self.get_unregister_approval_task_client()
        source_application = self.env['amr.resource.helper'].get_issuer()
        if self:
            for approval_task in self:
                result = client.prepare_payload(
                    source_model=approval_task.transaction_model_name,
                    source_res_id=approval_task.transaction_id,
                    source_application=source_application,
                    request_type='unregister_approval',
                    request_datetime=fields.Datetime.now(),
                )
                result.dispatch_send()
        else:
            result = client.prepare_payload(
                source_model=kwargs.get('transaction_model_name'),
                source_res_id=kwargs.get('transaction_id'),
                source_application=source_application,
                request_type='unregister_approval',
                request_datetime=fields.Datetime.now(),
            )
            result.dispatch_send()
