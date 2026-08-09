# -*- coding: utf-8 -*-

import ast
from odoo import api, fields, models


class ApprovalTaskAggregator(models.Model):
    _name = "approval.task.aggregator"
    _description = "Accept Approval Aggregation Task Other System"
    _order = 'request_approval_task_datetime desc,id desc'

    source_number = fields.Char('Number')
    source_document = fields.Char('Type')
    source_description = fields.Char('Description')
    source_application = fields.Char()
    source_model = fields.Char()
    source_res_id = fields.Integer()
    source_url = fields.Char()
    source_local = fields.Boolean(readonly=True)
    requester_id = fields.Many2one(
        'res.users', 'Requester',
        ondelete='set null',
        help="User who requested the approval."
    )
    user_ids = fields.Many2many(
        'res.users', 'approval_task_aggregator_users_rel', 'approval_task_aggregator_id', 'user_id',
    )
    request_approval_datetime = fields.Datetime(
        string='Request Approval Date', readonly=True, default=fields.Datetime.now,
        help="Waktu yang dicatat ketika Requester Request Approval."
    )
    request_approval_task_datetime = fields.Datetime(
        string="Request Approval Task Date",
        readonly=True,
        default=fields.Datetime.now,
        help="Waktu yang dicatat ketika Approval Task diberikan pada user atau group tertentu.",
    )
    company_id = fields.Many2one(
        'res.company'
    )

    @api.model
    def get_field_prepare(self):
        return ['source_number', 'source_document', 'source_description', 'source_application',
                'source_model', 'source_res_id', 'source_url', 'source_local', 'requester_id',
                'user_ids', 'request_approval_datetime', 'request_approval_task_datetime',
                'company_id', ]

    def api_get_approvals(self, user_email=None, offset=0, limit=None, order=None, size=False, **data):

        if isinstance(limit, str):
            limit = int(limit)
        if isinstance(offset, str):
            offset = int(offset)
        domain = []
        if user_email:
            domain.append(('user_ids.partner_id.email', '=', user_email))

        source_application = data.get('source_application')
        if source_application:
            domain.append(('source_application', '=', source_application))

        source_model = data.get('source_model')
        if source_model:
            domain.append(('source_model', '=', source_model))
        source_res_id = data.get('source_res_id')
        if source_res_id:
            domain.append(('source_res_id', '=', source_res_id))
        source_number = data.get('source_number')
        if source_number:
            domain.append(('source_number', 'ilike', source_number))

        source_document = data.get('source_document')
        if source_document:
            domain.append(('source_document', 'ilike', source_document))

        source_originator_name = data.get('source_originator_name')
        if source_originator_name:
            domain.append(('requester_id.name', 'ilike', source_originator_name))

        if 'filters' in data:
            domain += ast.literal_eval(data['filters'])

        result = {
            'status': 'success',
            'offset': offset,
            'count': 0,
        }
        if size:
            count = self.search(domain, order=order, count=True)
            result['size'] = count
            if count < 1:
                result.update(
                    message='Data not found',
                    results=[]
                )
                return result

        approvals = self.search(domain, limit=limit, offset=offset, order=order)
        if approvals:
            data_list = [rec.api_output_dict() for rec in approvals]
            result.update(
                count=len(data_list),
                message='Data found',
                results=data_list
            )
        else:
            result.update(
                message='Data not found',
                results=[]
            )

        return result

    def api_output_dict(self):
        rec = self.ensure_one()
        result = {
            'id': rec.id,
            'access_url': rec.id,
            'request_datetime': rec.request_approval_date or None,
            'request_task_datetime': rec.request_approval_task_date or None,
            'source_application': rec.source_application or None,
            'source_model': rec.source_model or None,
            'source_res_id': rec.source_res_id or None,
            'source_number': rec.source_number or None,
            'source_document': rec.source_document or None,
            'source_description': rec.source_description or None,
            'source_originator_name': rec.requester_id.name or None,
            'source_url': rec.source_url or None
        }
        return result

    def create_or_update(self, **kwargs):
        source_local = kwargs.get('source_local', False)
        source_model = kwargs.get('source_model', False)
        source_res_id = kwargs.get('source_res_id', False)
        source_application = kwargs.get('source_application', False)
        data = {}

        def to_list_for_m2m(values):
            if isinstance(values, models.BaseModel):
                return values.ids
            elif isinstance(values, list):
                return values
            return []

        for key in self.get_field_prepare():
            value = kwargs.get(key, None)
            if value is not None:
                data[key] = value

        if 'user_ids' in kwargs:
            objects = kwargs.get('user_ids')
            if objects:
                data['user_ids'] = [(6, 0, to_list_for_m2m(objects))]
        else:
            data['user_ids'] = []
        domain = [
            ('source_res_id', '=', source_res_id),
            ('source_model', '=', source_model),
        ]
        if source_local:
            domain.append(('source_local', '=', source_local))
        else:
            domain.append(('source_application', '=', source_application))

        ata = self.search(domain)
        if ata:
            ata.sudo().write(data)
        else:
            self.sudo().create([data])

    def action_approval_transaction(self):
        if self.source_local:
            approval_task = self.env['approval.task'].get_approval_task(self.source_res_id, self.source_model)
            if approval_task:
                return approval_task.action_approval_transaction()
            else:
                self.sudo().unlink()
                return
        else:
            url = self.env.user.add_url_access_token(self.source_url, url_type='auto_login')
            return {
                "type": "ir.actions.act_url",
                "url": url,
                "target": "new",
            }
