# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ApprovalInstanceAbleMixin(models.AbstractModel):
    _name = 'approval.instance.able.mixin'

    approval_instance_id = fields.Many2one(
        'approval.instance',
        compute="compute_approval_instance_id"
    )
    access_approval = fields.Boolean(
        compute="compute_access_approval",
        search="search_filter_access_approval",
    )
    flag_reject = fields.Boolean()
    note_reject = fields.Text()
    approval_line_for_document = fields.Many2many(
        'approval.audit.log',
        string='Approval Line for Document',
        compute='_compute_approval_line_for_document',
        help="Approval line untuk di pakai di dokument lembar pengesahan"
    )
    notification_to_user_id = fields.Many2one(
        'res.users', string='Notification to User',
        compute="_compute_notification_to_user_id",
        help="User who will receive the notification.",
    )

    @api.depends_context('notification_to_user')
    def _compute_notification_to_user_id(self):
        for rec in self:
            rec.notification_to_user_id = self.env.context.get('notification_to_user', False)

    def _compute_approval_line_for_document(self):
        for rec in self:
            rec.approval_line_for_document = rec.approval_line_for_document.get_approval_line_for_document(
                self._name,
                rec.id
            )

    def unregister_approval_task(self, skip_create_approval_log=True, **kwargs):
        self.unregister_from_approval_task(skip_create_approval_log=skip_create_approval_log, **kwargs)

    def register_approval_task(self, **kwargs):
        return self.register_to_approval_task(**kwargs)

    def get_internal_number(self):
        """
        Default internal description
        """
        if self and hasattr(self, 'name') and self.name:
            return self.name
        return self.display_name

    def get_internal_document(self):
        """
        Default internal document
        """
        if self and hasattr(self, '_description'):
            return self._description
        return None

    def get_internal_description(self):
        """
        Default internal description
        """
        if self and hasattr(self, '_description') and self._description and hasattr(self, 'name') and self.name:
            return f"{self._description} {self.name}"
        return None

    def _find_action_id(self, action_xmlid=None):
        if action_xmlid:
            try:
                return self.env.ref(action_xmlid).id
            except ValueError:
                return None
        else:
            action_id = None
            if hasattr(self, 'get_internal_action_id') and callable(self.get_internal_action_id):
                action = self.get_internal_action_id()
                if isinstance(action, str):
                    try:
                        action_id = self.env.ref(action).id
                    except ValueError:
                        return None
            else:
                action = self.env['ir.actions.act_window'].search([('res_model', '=', self._name)], limit=1)
                if action:
                    action_id = action.id
        return action_id

    def _find_menu_id(self, menu_xmlid=None, action_id=None):
        if menu_xmlid:
            try:
                return self.env.ref(menu_xmlid).id
            except ValueError:
                return None
        else:
            if hasattr(self, 'get_internal_menu_id') and callable(self.get_internal_menu_id):
                menu_id = self.get_internal_menu_id()
                if isinstance(menu_id, str):
                    try:
                        menu_id = self.env.ref(menu_id).id
                    except ValueError:
                        return None
            else:
                menu_id = None
                if action_id:
                    menu = self.env['ir.ui.menu'].search(
                        [('action', '=', f'ir.actions.act_window,{action_id}')],
                        limit=1
                    )
                    if menu:
                        menu_id = menu.id

                # Jika root_menu=True → naik ke menu paling atas
                if menu_id:
                    menu_rec = self.env['ir.ui.menu'].browse(menu_id)
                    while menu_rec.parent_id:
                        menu_rec = menu_rec.parent_id
                    return menu_rec.id

        return menu_id

    def get_internal_url(self, menu_xmlid=None, cids=None, skip_if_no_company=True, action_xmlid=None):
        """
        Generate backend URL untuk record ini.

        :param menu_xmlid: XMLID menu opsional
        :param cids: company IDs opsional
        :param skip_if_no_company: jika True dan company_id kosong, fallback ke env.company.id
        """
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        action_id = self._find_action_id(action_xmlid)
        menu_id = self._find_menu_id(menu_xmlid, action_id=action_id)
        # Tentukan cids
        if cids is None:
            if 'company_id' in self._fields:
                if self.company_id:
                    cids = self.company_id.id
                elif skip_if_no_company:
                    cids = self.env.company.id
                else:
                    cids = None
            else:
                cids = self.env.company.id

        menu_part = f"&menu_id={menu_id}" if menu_id else ""
        cids_part = f"&cids={cids}" if cids else ""
        action_path = f"&action={action_id}" if action_id else ""
        return f"{base_url}/web#id={self.id}&model={self._name}&view_type=form{menu_part}{cids_part}{action_path}"

    def unregister_from_approval_task(self, skip_create_approval_log=True, **kwargs):
        """
        Approval task as done
        """
        self.ensure_one()
        self.env['approval.instance'].create_or_get(self).unregister_approval_task_line(**kwargs)
        kwargs = dict(kwargs)
        kwargs.update(
            transaction_id=self.id,
            transaction_model_name=self._name,
        )
        self.env['approval.task'].approval_done(**kwargs)
        if not skip_create_approval_log:
            self.create_approval_log(**kwargs)

    def register_to_approval_task(self, **kwargs):
        """
        Register to approval task system
        """
        self.ensure_one()

        if 'transaction_object' not in kwargs:
            kwargs['transaction_object'] = self
        if 'transaction_id' in kwargs:
            kwargs.pop('transaction_id')
        if 'transaction_model_name' in kwargs:
            kwargs.pop('transaction_model_name')
        transaction_id = self.id
        transaction_model_name = self._name

        return self.env['approval.task'].approval_setup(
            transaction_id, transaction_model_name, **kwargs
        )

    def get_approval_transaction_task(self):
        return self.env['approval.task'].search([
            ('transaction_id', '=', self.id),
            ('transaction_model_name', '=', self._name),
        ], limit=1)

    def send_notification_approval(self, **kwargs):
        approval = self.get_approval_transaction_task()
        if approval:
            approval.send_notification(**kwargs)

    def create_approval_log(self, **kwargs):
        self.ensure_one()
        create_d = dict(kwargs)
        create_d['transaction_id'] = self.id
        create_d['transaction_model_name'] = self._name
        return self.env['approval.audit.log'].create_audit_log(**create_d)

    def unlink(self):
        list_ids = self.ids
        model_name = self._name
        result = super(ApprovalInstanceAbleMixin, self).unlink()
        self.env['approval.task'].search(
            [('transaction_model_name', '=', model_name), ('transaction_id', 'in', list_ids)]).unlink()
        return result

    def get_approval_template(self):
        return self.env['approval.template'].search_template(transaction_model_name=self._name)

    def write(self, vals):
        if self.env.context.get('__skip_approval_status'):
            return super().write(vals)
        approval_template = self.get_approval_template()
        state_field = None
        old = None
        if approval_template and approval_template.state_field:
            state_field = approval_template.state_field
            if state_field in vals:
                old = {r.id: r.state for r in self}
        # handling bila keluar approval
        result = super().write(vals)
        if old and state_field:
            state_waiting_approvals = approval_template.get_state_waiting_approvals()
            for rec in self:
                state_approval = getattr(rec, state_field)
                if old[rec.id] in state_waiting_approvals and state_approval not in state_waiting_approvals:
                    _logger.info(f"Keluar dari waiting_approval {rec.id}")
                    rec.unregister_approval_task(skip_create_approval_log=True)
                elif (approval_template.auto_register_approval_task
                      and not self.env.context.get('__skip_auto_register_approval_task_line_status')
                      and old[rec.id] not in state_waiting_approvals
                      and state_approval in state_waiting_approvals
                ):
                    rec.register_to_approval_task(
                        approval_template=approval_template,
                        transaction_object=rec,
                    )

        return result

    def get_approval_users_signature(self):
        self.ensure_one()
        signatures = [{
            'sign_title': 'Created by',
            'sign_user': self.create_uid,
            'approval_task_line': False,
        }]
        all_approval_task_line = self.get_all_approval_task_line()
        if all_approval_task_line:
            for line in all_approval_task_line:
                signatures.append({
                    'sign_title': line.sign_title or 'Approved by',
                    'sign_user': line.user_execution_id,
                    'approval_task_line': line,
                })

        return signatures

    def get_all_to_approve_ids(self):
        # get all ids to approve by transaction model
        approval_task = self.env['approval.task'].with_context(
            __transaction_model_name=self._name
        ).search(
            [('user_have_access_to_approval', '=', True)]
        )
        return list(approval_task.mapped('transaction_id'))

    @api.depends_context("uid")
    @api.depends('approval_instance_id')
    def compute_access_approval(self):
        for rec in self:
            rec.access_approval = rec.approval_instance_id and rec.approval_instance_id.access_approval

    @api.model
    def search_filter_access_approval(self, operator, value):
        approval_template = self.get_approval_template()
        domain = approval_template.get_domain_waiting_status()
        datas = self.search(domain)
        ids = [data.id for data in datas if data.access_approval]
        return [('id', 'in', ids)]

    def action_ensure_approval_instance(self):
        rec = self.ensure_one()
        approval_instance = rec.approval_instance_id.create_or_get(transaction=rec)
        return {
            'type': 'ir.actions.act_window',
            'name': self._name,
            'res_model': approval_instance._name,
            'res_id': approval_instance.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'create': 0,
                'edit': 0,
            }
        }

    def ensure_approval_instance(self):
        rec = self.ensure_one()
        return rec.approval_instance_id.create_or_get(transaction=rec)

    def action_request_approval(self):
        rec = self.ensure_one()
        approval_instance = rec.ensure_approval_instance()
        return approval_instance.request_approval()

    def action_approve(self):
        rec = self.ensure_one()
        approval_instance = rec.ensure_approval_instance()
        return approval_instance.action_approve()

    def action_reject(self):
        rec = self.ensure_one()
        approval_instance = rec.ensure_approval_instance()
        return approval_instance.action_reject()

    def reject_from_popup_reject(self, **kwargs):
        rec = self.ensure_one()
        approval_instance = rec.ensure_approval_instance()
        return approval_instance.reject_from_popup_reject(**kwargs)

    def action_clear_approval(self):
        rec = self.ensure_one()
        approval_instance = rec.ensure_approval_instance()
        return approval_instance.clear_approval()

    def compute_approval_instance_id(self):
        for rec in self:
            rec.approval_instance_id = self.approval_instance_id.get_instance_for_transaction(self._name, rec.id)

    def get_next_approval_task_line(self):
        rec = self.ensure_one()
        approval_instance = rec.approval_instance_id.get_instance_for_transaction(self._name, rec.id)
        return approval_instance and approval_instance.get_next_approval_task_line()

    def get_last_approval_task_line(self):
        rec = self.ensure_one()
        approval_instance = rec.approval_instance_id.get_instance_for_transaction(self._name, rec.id)
        return approval_instance and approval_instance.get_last_approval_task_line()

    def get_users_approval_notification(self, **kwargs):
        return self.get_next_approval_task_line().get_users_for_notification(**kwargs)

    def send_approval_notification(self, **kwargs):
        rec = self.ensure_one()
        notification_template = kwargs.get(
            "notification_template") or rec.approval_instance_id.get_notification_approval()
        users = kwargs.get("users") or rec.get_users_for_notification(**kwargs)
        if notification_template:
            notification_template.send_notification_to_users(users, rec.id, **kwargs)

    def is_status_waiting_approval(self):
        rec = self.ensure_one()
        approval_instance = rec.approval_instance_id.create_or_get(rec)
        return approval_instance and approval_instance.is_status_waiting_approval()

    def get_all_approval_task_line(self):
        return self.approval_instance_id.get_all_approval_task_line()

    def get_notification_approval(self):
        return self.approval_template_id.notification_approval_id
