# -*- coding: utf-8 -*-

import traceback
import json

from odoo import api, fields, models


class ApprovalTaskRequest(models.Model):
    _name = "approval.task.request"
    _order = 'request_datetime,id'

    state = fields.Selection([
        ('accept', 'accept'),
        ('process', 'Process'),
        ('done', 'Done'),
        ('expired', 'Expired'),
        ('error', 'Error'),
    ])
    request_type = fields.Selection([
        ('register_approval', 'Register'),
        ('unregister_approval', 'Un-Register'),
    ])
    request_datetime = fields.Datetime(default=fields.Datetime.now)
    source_application = fields.Char()
    source_model = fields.Char()
    source_res_id = fields.Integer()
    payload = fields.Text()
    errors_message = fields.Char()
    last_error = fields.Datetime()

    def api_create_request(self, **data):
        approvals = self.create_request(**data)
        if approvals:
            result = {
                'status': 'success',
                'message': 'Process IDS %s' % approvals.ids,
            }
        else:
            result = {
                'status': 'success',
                'message': 'Data not found',
            }
        return result

    def create_request(self, request_type=None, **kwargs):
        source_application = kwargs.get('source_application')
        source_model = kwargs.get('source_model')
        source_res_id = int(kwargs.get('source_res_id'))
        create_request = self.create([{
            'request_type': request_type,
            'source_application': source_application,
            'source_model': source_model,
            'source_res_id': source_res_id,
            'payload': json.dumps(kwargs)
        }])[0]
        return create_request.process()

    def process(self):
        request_type = self.request_type
        create_request = self
        try:
            data = {
                'source_application': self.source_application,
                'source_model': self.source_model,
                'source_res_id': self.source_res_id,
            }
            if 'unregister_approval' == request_type:
                create_request.unregister_approval(data)
            elif 'register_approval' == request_type:
                create_request.register_approval(data)
        except Exception:
            create_request.write({
                'state': 'error',
                'errors_message': traceback.format_exc(),
                'last_error': fields.Datetime.now()
            })

        return create_request

    def action_retry(self):
        return self.process()

    def action_mark_done(self):
        self.write({'state': 'done'})

    def action_reset(self):
        self.write({'state': 'process'})

    # -------------------------------------------------------
    # PROCESS ACCEPT DATA
    # -------------------------------------------------------
    def get_users_from_client(self, data):
        user_list = data.get('user_list')
        to_users = self.env['res.users'].browse()
        if user_list:
            for user_email in user_list:
                to_users |= self.get_user_from_client(user_email)
        return to_users

    def get_user_from_client(self, user_email):
        res_users = self.env['res.users']
        if isinstance(user_email, str):
            return res_users.search(['|', ('partner_id.email', '=', user_email), ('login', '=', user_email)], limit=1)
        elif isinstance(user_email, dict):
            return (
                    self.get_user_from_client(user_email.get('login')) or
                    self.get_user_from_client(user_email.get('email'))
            )
        else:
            return res_users.browse()

    def get_company_from_client(self, company_name):
        res_company = self.env['res.company']
        if isinstance(company_name, str):
            return res_company.search([('name', '=', company_name)], limit=1)
        elif isinstance(company_name, dict):
            return (
                    self.get_user_from_client(company_name.get('name')) or
                    self.get_user_from_client(company_name.get('code'))
            )
        else:
            return res_company.browse()

    def unregister_approval(self, data):
        source_application = data.get('source_application')
        source_model = data.get('source_model')
        source_res_id = int(data.get('source_res_id'))
        domain = [('source_application', '=', source_application),
                  ('source_model', '=', source_model),
                  ('source_res_id', '=', source_res_id)]
        approval_users = self.env["approval.task.aggregator"].search(domain)
        approval_users.unlink()
        return approval_users

    def register_approval(self, data):
        return self.create_or_update_approval_user(**data)

    def create_or_update_approval_user(self, **kwargs):
        self.state = 'process'
        source_company = kwargs.get('source_company')
        source_requester = kwargs.get('source_requester')
        source_application = kwargs.get('source_application')
        source_model = kwargs.get('source_model')
        source_res_id = kwargs.get('source_res_id')
        request_datetime = kwargs.get('request_datetime')
        if request_datetime:
            request_datetime = fields.Datetime.to_datetime(request_datetime)
        else:
            request_datetime = fields.Datetime.now()
        requester = self.get_user_from_client(source_requester)
        company = self.get_company_from_client(source_company)
        approval_user = self.env["approval.task.aggregator"].search([
            ('source_model', '=', source_model),
            ('source_res_id', '=', source_res_id),
            ('source_application', '=', source_application),
        ])
        accept_key = ['source_application', 'source_model', 'source_res_id',
                      'source_number', 'source_document', 'source_url']
        data = {k: v for k, v in kwargs.items() if k in accept_key}
        data['source_url'] = kwargs.get('source_url') or kwargs.get('url')
        if requester:
            data['requester_id'] = requester.id
        if company:
            data['company_id'] = company.id
        users = self.get_users_from_client(data)
        data['user_ids'] = users.ids

        if self.env.context.get('__source_local'):
            data['source_local'] = True
        data['request_approval_task_datetime'] = request_datetime

        if approval_user:
            if request_datetime and approval_user.request_approval_task_datetime <= request_datetime:
                approval_user.write(data)
            else:
                self.write({
                    'state': 'expired',
                    'errors_message': "Skip",
                })
                return approval_user
        else:
            approval_user = self.env["approval.task.aggregator"].create(data)

        self.write({
            'state': 'done',
            'errors_message': False,
        })
        return approval_user
