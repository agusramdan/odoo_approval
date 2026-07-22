# -*- coding: utf-8 -*-

import logging

from dateutil.relativedelta import relativedelta
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.models import BaseModel

from ..tools.utils import have_method

_logger = logging.getLogger(__name__)


class ApprovalTask(models.Model):
    _name = 'approval.task'
    _inherit = 'approval.transaction.able.mixin'
    _description = 'This is Approval Task for Approval helper waiting approval'
    _order = 'request_approval_task_date, create_date desc'

    name = fields.Char('Name')
    document = fields.Char()
    description = fields.Char()
    url = fields.Char(string="URL")
    date = fields.Datetime(
        string='Request Date', readonly=True, default=fields.Datetime.now,
        help="Waktu yang dicatat ketika Requester Request Approval."
    )
    request_approval_task_date = fields.Datetime(
        string="Request Approval Task Date",
        readonly=True,
        default=fields.Datetime.now,
        help="Waktu yang dicatat ketika Approval Task diberikan pada user atau group tertentu.",
    )
    aging = fields.Integer(
        compute="_compute_aging_display",
        string="Aging"
    )

    aging_display = fields.Char(
        compute="_compute_aging_display"
    )

    transaction_id = fields.Integer(
        'Transaction ID'
    )
    transaction_model_name = fields.Char(
        'Transaction Model Name',
    )
    company_id = fields.Many2one(
        'res.company'
    )
    user_ids = fields.Many2many(
        'res.users', 'approval_task_users_rel', 'approval_task_id', 'user_id',
    )
    group_ids = fields.Many2many(
        'res.groups', 'approval_task_groups_rel', 'approval_task_id', 'group_id',
        help="Groups of users who can approve this task"
    )
    # See approval.responsible for maping detail
    responsible_user_id = fields.Many2one(
        'res.users', 'Responsible',
        ondelete='set null',
        help="User who take Responsible the approval. Related with respnsible model. "
             "ex: Department have manager when manager change responsible change to. "
    )
    responsible_model = fields.Char('Responsible Model')
    responsible_res_id = fields.Integer('Responsible ID')
    requester_id = fields.Many2one(
        'res.users', 'Requester',
        default=lambda self: self.env.user,
        ondelete='set null',
        help="User who requested the approval."
    )
    user_have_access_to_approval = fields.Boolean(
        string="Can Approve",
        compute='_compute_user_have_access_to_approval',
        search='search_filter_user_have_access_to_approval',
    )
    transaction_display_name = fields.Char(
        'Name',
        compute='_compute_transaction_display_name',
        compute_sudo=True,
    )
    approval_res_id = fields.Integer(
        'Approval ID'
    )
    approval_model = fields.Char(
        'Approval Model',
    )
    approval_instance_id = fields.Many2one(
        'approval.instance',
        ondelete='set null',
    )
    approval_user_ids = fields.Many2many(
        'res.users', compute='_compute_approval_user_ids', compute_sudo=True
    )

    assignment_able = fields.Boolean(
        compute='_compute_assignment_able'
    )
    notification_approval_id = fields.Many2one(
        'notification.template',
        string='Notification',
        ondelete='set null',
    )
    notification_reminder_id = fields.Many2one(
        'notification.template',
        string='Reminder',
        ondelete='set null',
        help="Notification template used for reminder notifications."
    )
    reminder_last_datetime = fields.Datetime(
        'Last Reminder',
        readonly=True,
    )
    reminder_next_datetime = fields.Datetime(
        'Next Reminder',
        readonly=True,
    )
    reminder_count = fields.Integer(
        'Count Reminder',
    )

    user_delegation_id = fields.Many2one(
        'user.delegation',
        compute='_compute_user_delegation'
    )

    @api.depends("request_approval_task_date")
    def _compute_aging_display(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.request_approval_task_date:
                rec.aging = 0
                rec.aging_display = ""
                continue
            request_date = fields.Datetime.context_timestamp(
                rec,
                rec.request_approval_task_date
            ).date()
            days = (today - request_date).days
            rec.aging = days
            if days < 30:
                rec.aging_display = "%s Days" % days
            else:
                rec.aging_display = "%s Months" % (days // 30)

    def cron_reminder(self):
        reminders = self.search([('reminder_next_datetime', '<', fields.Datetime.now())], limit=1000)
        for rem in reminders:
            rem.send_reminder()

    def send_reminder(self, **kwargs):
        self.ensure_one()
        try:
            approval_instance = kwargs.get(
                'approval_instance') or self.approval_instance_id.get_instance_for_transaction(
                self.transaction_model_name, self.transaction_id
            )
            approval_template = kwargs.get('approval_template') or approval_instance.approval_template_id
            kwargs['reminder_count'] = reminder_count = self.reminder_count + 1

            notification_approval = kwargs.get("notification_approval")
            if "notification_approval_id" in kwargs:
                notification_approval = self.env['notification.template'].browse(kwargs.get("notification_approval_id"))

            if not notification_approval:
                notification_approval = self.notification_reminder_id or approval_template.notification_reminder_id

            if not notification_approval:
                notification_approval = self.notification_approval_id or approval_template.notification_approval_id

            notification_log = None
            kwargs['approval_task_id'] = self.id
            if notification_approval:
                res_id, model_name = self.get_res_id_for_notification(notification_approval, **kwargs)
                if res_id:
                    self.write({
                        'reminder_count': reminder_count,
                        'reminder_last_datetime': fields.Datetime.now(),
                        'reminder_next_datetime': approval_template.get_next_reminder_datetime(),
                    })
                    users = self.get_users_for_notification(**kwargs)
                    if self.requester_id:
                        notification_approval = notification_approval.with_user(self.requester_id)
                    notification_log = notification_approval.send_notification_to_users(
                        users, res_id, **kwargs
                    )

            if notification_log:
                reminder_datetime = fields.Datetime.now()
                reminders = [{
                    'user_id': self.requester_id.id or self.env.user.id,
                    'transaction_id': self.transaction_id,
                    'transaction_model_name': self.transaction_model_name,
                    'request_approval_task_date': self.request_approval_task_date,
                    'reminder_datetime': reminder_datetime,
                    'reminder_count': reminder_count,
                    'receiver_id': notif.receiver_id.id,
                    'notification_log_id': notif.id
                } for notif in notification_log]
                self.env["reminder.log"].sudo().create(reminders)
            elif reminder_count:
                self.write({'reminder_count': reminder_count - 1, })
        except Exception:
            _logger.exception("skip error")

        finally:
            _logger.info("Send Reminder done")

    def _compute_approval_user_ids(self):
        for rec in self:
            rec.approval_user_ids = rec.get_users_for_approval()

    def check_access_rights_and_rule(self, user_and_delegator):
        rec = self.ensure_one()
        record = rec.sudo().get_transaction_object()
        if not record:
            return False
        can_access = False
        for user in user_and_delegator:
            try:
                record_check = record.with_user(user)
                record_check.check_access_rights('read')
                record_check.check_access_rule('read')
                return True
            except AccessError:
                can_access = False

        return can_access

    def _compute_user_have_access_to_approval(self):
        """Hitung apakah user login punya akses approve/reject."""
        current_user = self.env.user
        for rec in self:
            rec.user_have_access_to_approval = current_user.id in rec.get_users_for_approval().ids

    def search_filter_user_have_access_to_approval(self, operator, value):
        current_uid = self.env.user.id
        cr = self._cr
        ids = set()
        delegators = self.env.user.get_delegators()
        transaction_model_name = self.env.context.get('__transaction_model_name')
        model_filter = ""
        if transaction_model_name:
            model_filter = f" transaction_model_name = '{transaction_model_name}' AND "
        if delegators:
            user_and_delegator = self.env.user | delegators
            user_filter = f"IN ({', '.join(str(d.id) for d in user_and_delegator)})"
        else:
            user_and_delegator = self.env.user
            user_filter = f"= {current_uid}"
        # CASE: Multi User (M2M)
        if 'user_ids' in self._fields:
            rel_table = self._fields['user_ids'].relation
            col_this = self._fields['user_ids'].column1
            col_user = self._fields['user_ids'].column2
            cr.execute(f"""
                SELECT DISTINCT at.id 
                FROM approval_task at 
                JOIN {rel_table} mg ON at.id = mg.{col_this}
                WHERE {model_filter} {col_user} {user_filter}
            """)
            ids.update(r[0] for r in cr.fetchall())

        # CASE: Multi Group (M2M)
        if 'group_ids' in self._fields:
            rel_table = self._fields['group_ids'].relation
            col_this = self._fields['group_ids'].column1
            col_group = self._fields['group_ids'].column2
            cr.execute(f"""
                SELECT DISTINCT at.id 
                FROM approval_task at
                JOIN {rel_table} mg ON at.id = mg.{col_this}
                JOIN res_groups_users_rel gu ON gu.gid = mg.{col_group}
                WHERE {model_filter} gu.uid {user_filter}
            """, (current_uid,))
            ids.update(r[0] for r in cr.fetchall())
        if (operator == '=' and value) or (operator == '!=' and not value):
            if ids and self.env.context.get('__transaction_data_check_access_rights_and_rule'):
                ids = [rec.id for rec in self.browse(list(ids)) if rec.check_access_rights_and_rule(user_and_delegator)]
            else:
                ids = list(ids)
            return [('id', 'in', ids)]
        else:
            return [('id', 'not in', list(ids))]

    def get_users(self):
        """Return daftar user unik sesuai type_approval"""
        self.ensure_one()
        users = self.env['res.users'].browse()
        if self.user_ids:
            users |= self.user_ids

        if self.group_ids:
            users |= self.group_ids.mapped('users')

        return users

    def get_transaction_object(self):
        if not self.transaction_id or not self.transaction_model_name:
            return None

        if self.transaction_id:
            return self.env[self.transaction_model_name].browse(self.transaction_id)

        return self.env[self.transaction_model_name].browse()

    def approval_done(self, **kwargs):
        if self:
            records = self
        else:
            transaction_id = kwargs.get('transaction_id')
            transaction_model_name = kwargs.get('transaction_model_name')
            if transaction_model_name and transaction_id:
                records = self.search([('transaction_id', '=', transaction_id),
                                       ('transaction_model_name', '=', transaction_model_name), ])
            else:
                return True
        return records.sudo().unlink()

    @api.model
    def get_field_prepare(self):
        return ['name', 'document', 'description', 'url', 'date', 'view_name', 'requester_id', 'company_id',
                'approval_res_id', 'approval_model', 'approval_instance_id', 'request_approval_task_date',
                'reminder_count', 'reminder_last_datetime', 'reminder_next_datetime', 'reminder_next_datetime'
                ]

    @api.model
    def prepare_data(self, **kwargs):
        data = dict()

        def to_list_for_m2m(values):
            if isinstance(values, BaseModel):
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
        if 'group_ids' in kwargs:
            objects = kwargs.get('group_ids')
            if objects:
                data['group_ids'] = [(6, 0, to_list_for_m2m(objects))]
        else:
            data['group_ids'] = []
        if 'approval_instance_id' not in data:
            approval_instance = kwargs.get('approval_instance', 0)
            approval_instance and data.update(approval_instance_id=int(approval_instance))

        notification_approval = kwargs.get("notification_approval_id")
        if notification_approval:
            data['notification_approval_id'] = notification_approval

        notification_reminder = kwargs.get("notification_reminder_id")
        if notification_reminder:
            data['notification_reminder_id'] = notification_reminder

        return data

    def prepare_create(self, **kwargs):
        transaction_id = kwargs.get('transaction_id')
        transaction_model_name = kwargs.get('transaction_model_name')
        transaction_object = kwargs.get('transaction_object') or self.env[transaction_model_name].sudo().browse(
            transaction_id)
        kw = self.prepare_data(**kwargs) or {}
        if transaction_object:
            if 'name' not in kw and have_method(transaction_object, 'get_internal_number'):
                kw['name'] = transaction_object.get_internal_number()
            if not kw.get('name'):
                kw['name'] = getattr(transaction_object, 'name', "no name")
            if not kw.get('document') and have_method(transaction_object, 'get_internal_document'):
                kw['document'] = transaction_object.get_internal_document()
            if not kw.get('name'):
                kw['document'] = getattr(transaction_object, '_name', "no desc")

            if not kw.get('description') and have_method(transaction_object, 'get_internal_description'):
                kw['description'] = transaction_object.get_internal_description()

            if not kw.get('requester_id') and have_method(transaction_object, 'get_internal_requester_id'):
                kw['requester_id'] = transaction_object.get_internal_requester_id()

            if 'url' not in kw and have_method(transaction_object, 'get_internal_url'):
                kw['url'] = transaction_object.get_internal_url()

            if 'company_id' not in kw and hasattr(transaction_object, 'company_id'):
                kw['company_id'] = transaction_object.company_id.id

            if not kw.get('transaction_id'):
                kw['transaction_id'] = transaction_object.id

            if not kw.get('transaction_model_name'):
                kw['transaction_model_name'] = transaction_object._name
        else:
            raise UserError("No Transaction")

        return kw

    def prepare_write(self, **kwargs):
        transaction_id = kwargs.get('transaction_id')
        transaction_model_name = kwargs.get('transaction_model_name')
        transaction_object = kwargs.get('transaction_object') or self.env[transaction_model_name].sudo().browse(
            transaction_id)
        kw = self.prepare_data(**kwargs) or {}
        if self and transaction_object:
            rec = self.ensure_one()
            if not rec.name and 'name' not in kw and have_method(transaction_object, 'get_internal_number'):
                kw['name'] = transaction_object.get_internal_number()

            if (
                    not rec.document
                    and not kw.get('document')
                    and have_method(transaction_object, 'get_internal_document')
            ):
                kw['document'] = transaction_object.get_internal_document()

            if (
                    not rec.description
                    and not kw.get('description')
                    and have_method(transaction_object, 'get_internal_description')
            ):
                kw['description'] = transaction_object.get_internal_description()

            if (
                    not rec.requester_id
                    and not kw.get('requester_id')
                    and have_method(transaction_object, 'get_internal_requester_id')
            ):
                kw['requester_id'] = transaction_object.get_internal_requester_id()

            if not rec.url and 'url' not in kw and have_method(transaction_object, 'get_internal_url'):
                kw['url'] = transaction_object.get_internal_url()

            if not rec.company_id and 'company_id' not in kw and hasattr(transaction_object, 'company_id'):
                kw['company_id'] = transaction_object.company_id.id

        if not kw.get('user_ids'):
            kw['user_ids'] = [(5, 0, 0)]
        if not kw.get('group_ids'):
            kw['group_ids'] = [(5, 0, 0)]

        return kw

    def get_approval_task(self, transaction_id, transaction_model_name):
        return self.search(
            [('transaction_id', '=', transaction_id), ('transaction_model_name', '=', transaction_model_name)],
            limit=1,
        )

    def approval_setup(self, transaction_id, transaction_model_name, reset_request_approval_task_date=True,
                       reset_reminder=True, **kwargs):
        approval_task = self.get_approval_task(transaction_id, transaction_model_name)
        prepare_dict = dict(kwargs)
        prepare_dict.update(
            transaction_id=transaction_id,
            transaction_model_name=transaction_model_name,
        )

        approval_instance = kwargs.get('approval_instance') or self.approval_instance_id.get_instance_for_transaction(
            self.transaction_model_name, self.transaction_id
        )
        approval_template = kwargs.get('approval_template') or approval_instance.approval_template_id
        approval_template_line = kwargs.get('approval_template_line') or approval_template.approval_template_line_id
        prepare_dict['approval_template'] = approval_template
        prepare_dict['approval_instance'] = approval_instance
        prepare_dict['approval_template_line'] = approval_template_line
        approval_task_line = kwargs.get('approval_task_line')
        if not approval_task_line and approval_template_line:
            approval_task_line = approval_template_line.get_next_approval_task_line(**prepare_dict)

        if not approval_task_line and approval_template:
            approval_task_line = approval_template.get_next_approval_task_line(
                **prepare_dict
            )
        if approval_task_line:
            prepare_dict['approval_task_line'] = approval_task_line

        if isinstance(approval_task_line, models.BaseModel):
            prepare_dict['approval_model'] = approval_task_line._name
            prepare_dict['approval_res_id'] = approval_task_line.id

        if not prepare_dict.get('user_ids') and not prepare_dict.get('group_ids'):
            if have_method(approval_task_line, "prepare_approval_task_dict"):
                prepare_dict.update(approval_task_line.prepare_approval_task_dict() or {})
            elif approval_template_line:
                prepare_dict.update(approval_template_line.get_approver_data(**prepare_dict) or {})
            elif approval_template:
                prepare_dict.update(approval_template.get_approver_data(**prepare_dict) or {})

        if reset_request_approval_task_date or reset_reminder:
            reset_reminder = True
            prepare_dict['request_approval_task_date'] = fields.Datetime.now()

        if reset_reminder:
            if approval_template.reminder_interval_number > 0:
                reminder_next_datetime = approval_template.get_next_reminder_datetime()
            else:
                # jika 0 maka remainder disable
                reminder_next_datetime = False
            prepare_dict.update(
                request_approval_task_date=fields.Datetime.now(),
                reminder_count=0,
                reminder_last_datetime=False,
                reminder_next_datetime=reminder_next_datetime
            )

        if approval_task:
            write_dict = approval_task.prepare_write(**prepare_dict)
            approval_task.sudo().write(write_dict)
        else:
            create_dict = self.prepare_create(**prepare_dict)
            approval_task = self.sudo().create(create_dict)
        if not kwargs.get('skip_send_notification'):
            approval_task.send_notification(**kwargs)
        approval_task.send_bus_notification(**kwargs)
        prepare_dict['approval_task'] = approval_task
        approval_template_line.start_waiting_approval(**prepare_dict)

        return approval_task

    def action_approval_transaction(self):
        transaction_object = self.get_transaction_object()
        if transaction_object and have_method(transaction_object, 'action_approval_transaction'):
            win_dict = transaction_object.action_approval_transaction()
            if win_dict:
                return win_dict
        return super(ApprovalTask, self).action_approval_transaction()

    def _compute_transaction_display_name(self):
        for rec in self:
            obj = rec.get_transaction_object()
            rec.transaction_display_name = obj and obj.display_name or rec.name or rec.display_name

    def get_users_for_notification(self, **kwargs):
        record = self.ensure_one()
        users = kwargs.get('users')
        if not isinstance(users, models.BaseModel):
            users = record.get_users()
        if users:
            return users.get_users_for_notification(company=self.company_id)
        else:
            return users

    def get_users_for_approval(self, **kwargs):
        record = self.ensure_one()
        users = kwargs.get('users')
        if not isinstance(users, models.BaseModel):
            users = record.get_users()
        if users:
            return users.get_users_for_approval(company=self.company_id)
        else:
            return users

    def get_users_for_mobile_approval(self, **kwargs):
        record = self.ensure_one()
        return record.get_users_for_approval(**kwargs)

    def send_to_mobile_approval(self, **kwargs):
        pass

    def get_res_id_for_notification(self, notification_approval, **kwargs):
        self.ensure_one()
        res_id = None
        model_name = None
        if notification_approval:
            model_name = notification_approval.model
            if model_name:
                if self.transaction_model_name == model_name:
                    res_id = self.transaction_id
                elif self._name == model_name:
                    res_id = self.id

        return res_id, model_name

    def send_notification(self, **kwargs):
        self.ensure_one()
        notification_log = None
        try:
            approval_instance = kwargs.get(
                'approval_instance') or self.approval_instance_id.get_instance_for_transaction(
                self.transaction_model_name, self.transaction_id
            )
            approval_template = kwargs.get('approval_template') or approval_instance.approval_template_id
            notification_approval = kwargs.get("notification_approval")
            if "notification_approval_id" in kwargs:
                notification_approval = self.env['notification.template'].browse(kwargs.get("notification_approval_id"))

            if not notification_approval:
                notification_approval = self.notification_approval_id or approval_template.notification_approval_id

            kwargs['approval_task_id'] = self.id
            if notification_approval:
                res_id, model_name = self.get_res_id_for_notification(notification_approval, **kwargs)
                if res_id:
                    users = self.get_users_for_notification(**kwargs)
                    if self.requester_id:
                        notification_approval = notification_approval.with_user(self.requester_id)
                    notification_log = notification_approval.send_notification_to_users(
                        users, res_id, approval_task_id=self.id
                    )
        except Exception:
            _logger.exception("skip error")
        finally:
            _logger.info("Send Notification done")
        return notification_log

    def send_bus_notification(self, **kwargs):
        pass

    def check_approval_task_status(self):
        if not self:
            return
        rec = self.ensure_one()
        if rec.approval_instance_id:
            rec.approval_instance_id.check_approval_task_status()
        elif not rec.transaction_model_name or not rec.transaction_id:
            rec.approval_done()
        else:
            transaction_object = rec.get_transaction_object()
            if transaction_object:
                if have_method(transaction_object, 'check_approval_task_status'):
                    transaction_object.check_approval_task_status()
            else:
                rec.approval_done()

    @api.depends_context("uid")
    def _compute_user_delegation(self):
        for rec in self:
            user_delegation = rec.get_user_delegation()
            if user_delegation:
                rec.user_delegation_id = user_delegation.id
            else:
                rec.user_delegation_id = None

    def get_user_delegation(self):
        rec = self.ensure_one()
        delegator_ids = rec.get_users().ids
        return self.env.user.get_delegation(delegator_ids, company_id=rec.company_id)

    def _compute_assignment_able(self):
        for rec in self:
            rec.assignment_able = self.approval_model in self.env and have_method(
                self.env[self.approval_model], "action_assignment"
            )

    def action_assign(self):
        return self.action_assignment()

    def action_reassign(self):
        return self.action_assignment()

    def action_assignment(self):
        self.ensure_one()
        if self.assignment_able and self.approval_res_id:
            return self.env[self.approval_model].browse(self.approval_res_id).action_assignment()
        else:
            raise UserError("Assignment not available for this task")

    def get_approval_task_line(self):
        return self.env[self.approval_model].browse(self.approval_res_id)

    def get_approval_template_line(self, **kwargs):
        return (
                kwargs.get('approval_template_line') or
                self.env['approval.template.line'].search_template_line_by_model(self.approval_model)
        )
