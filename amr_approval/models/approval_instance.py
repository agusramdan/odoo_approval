# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import datetime

from ..tools.utils import have_method, safe_call_method

_logger = logging.getLogger(__name__)


class ApprovalInstanceMixin(models.AbstractModel):
    _name = 'approval.instance.mixin'
    _inherit = ['approval.transaction.able.mixin']

    name = fields.Char("Number/Name")
    document = fields.Char("Document")
    description = fields.Char("Description")
    pdf_sign = fields.Selection(
        [('none', 'None'),
         ('approve_is_sign_pdf', 'Sign to Approve'),
         ('approve_form_sign_pdf', 'Sign from Approve'),
         ], default='none', help="""
            none : Not related pdf
            Approve to sign: When approve this instance will propagate to sign pdf.
            Approve from : Sign document will approve this instance when approve will redirect to sign authenticate.
            """
    )
    pdf_deep_link = fields.Char()
    approval_template_id = fields.Many2one('approval.template.mixin', ondelete='set null', )
    approval_task_id = fields.Many2one('approval.task', ondelete='set null', )
    model_id = fields.Many2one('ir.model', readonly=True, ondelete='set null', )
    model = fields.Char(related='model_id.model', store=True, readonly=True)
    requester_id = fields.Many2one('res.users', 'Requester')
    company_id = fields.Many2one('res.company', 'Company')
    url = fields.Char("URL")
    transaction_model_name = fields.Char(related='model_id.model', store=True)
    transaction_status = fields.Char()
    access_approval = fields.Boolean(
        string="Can Approve",
        compute="_compute_access_approval",
        store=False,
    )
    access_requester = fields.Boolean(
        string="Requester",
        compute="_compute_access_requester",
        store=False,
    )

    @api.depends_context('uid')
    def _compute_access_approval(self):
        for rec in self:
            if not rec.is_status_waiting_approval():
                rec.access_approval = False
                continue
            access_approval = False
            approval_task_line = rec.get_next_approval_task_line()
            if approval_task_line:
                if hasattr(approval_task_line, 'access_approval'):
                    access_approval = approval_task_line.access_approval
                elif isinstance(approval_task_line, models.BaseModel):
                    rec = rec.ensure_approval_template()
                    access_approval = rec.approval_template_id.get_access_approval(
                        approval_task_line=approval_task_line,
                        approval_template=rec.approval_template_id,
                        approval_instance=rec,
                    )
            rec.access_approval = access_approval

    @api.depends_context('uid')
    @api.depends('requester_id')
    def _compute_access_requester(self):
        current_user = self.env.user
        for rec in self:
            rec.access_requester = current_user == (rec.requester_id or rec.get_user_requestor())

    def name_get(self):
        res = []
        for rec in self.sudo():
            trx_object = rec.get_transaction_object()
            if trx_object:
                if rec.approval_template_id:
                    status = rec.get_transaction_status(trx_object)
                    name = f"{trx_object.display_name}-{rec.model_id.display_name}-{status}"
                else:
                    name = f"{trx_object.display_name}-{rec.model_id.display_name}"
            else:
                name = f"-{rec.model_id.display_name}-"
            res.append((rec.id, name))
        return res

    def get_state_waiting_approvals(self):
        rec = self.ensure_approval_template()
        return self.approval_template_id and rec.approval_template_id.get_state_waiting_approvals()

    def get_state_field(self):
        rec = self.ensure_approval_template()
        return rec.approval_template_id.get_state_field()

    def get_state_rejected(self):
        rec = self.ensure_approval_template()
        return self.approval_template_id and rec.approval_template_id.get_state_rejected()

    def get_state_approved(self):
        rec = self.ensure_approval_template()
        return self.approval_template_id and rec.approval_template_id.get_state_approved()

    def get_transaction_status(self, transaction=None):
        rec = self.ensure_approval_template()
        transaction = transaction or rec.get_transaction_object()
        return self.approval_template_id and self.approval_template_id.get_transaction_status(transaction)

    def get_user_requestor(self, transaction=None):
        rec = self.ensure_approval_template()
        transaction = transaction or rec.get_transaction_object()
        return self.approval_template_id and self.approval_template_id.get_user_requestor(transaction)

    def is_model_need_approval(self, transaction=None):
        rec = self.ensure_approval_template()
        transaction = transaction or rec.get_transaction_object()
        return self.approval_template_id and self.approval_template_id.is_model_need_approval(transaction)

    def is_status_request_approval(self, transaction=None):
        rec = self.ensure_approval_template()
        transaction = transaction or rec.get_transaction_object()
        return self.approval_template_id and self.approval_template_id.is_status_request_approval(transaction)

    def is_status_waiting_approval(self, transaction=None):
        rec = self.ensure_approval_template()
        transaction = transaction or rec.get_transaction_object()
        return self.approval_template_id and self.approval_template_id.is_status_waiting_approval(transaction)

    def ensure_approval_template(self):
        if not self:
            return self
        record = self.ensure_one()
        if not record.approval_template_id:
            record.approval_template_id = record.approval_template_id.search_template(
                transaction_model_name=self.transaction_model_name,
            )
        return record

    def create_or_get(
            self,
            transaction=None,
            transaction_model_name=None,
            transaction_id=None,
            raise_exception_without_template=True,
            **kwargs,
    ):
        if transaction:
            transaction_model_name = transaction._name
            transaction_id = transaction.id

        if not transaction_model_name:
            raise UserError("Model Name not set")
        if not transaction_id:
            raise UserError("ID not set")
        approval_template_id = self.approval_template_id.search_template(transaction_model_name=transaction_model_name)

        if not approval_template_id:
            if raise_exception_without_template:
                raise UserError("Approval Template not found.")
            return self.browse()

        approval_instance = self.get_instance_for_transaction(transaction_model_name, transaction_id) or self.create({
            'approval_template_id': approval_template_id.id,
            'transaction_model_name': transaction_model_name,
            'transaction_id': transaction_id,
        })
        return approval_instance.ensure_approval_template()

    def get_instance_for_transaction(self, transaction_model_name, transaction_id):
        for rec in self:
            if (
                    rec.transaction_model_name == transaction_model_name
                    and rec.transaction_id == transaction_id
            ):
                return rec
        return self.search(
            [
                ('model_id.model', '=', transaction_model_name),
                ('transaction_id', '=', transaction_id),
            ],
            limit=1,
        )

    @api.model_create_multi
    @api.returns('self', lambda value: value.id)
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('approval_template_id'):
                transaction_model_name = vals.pop('transaction_model_name')
                vals['model_id'] = self.env['ir.model'].search([('model', '=', transaction_model_name)]).id
            else:
                approval_template = self.approval_template_id.browse(vals.get('approval_template_id'))
                vals.update(approval_template.prepare_dict())
        return super(ApprovalInstanceMixin, self).create(vals_list)

    def get_all_approval_task_line(self):
        rec = self.ensure_approval_template()
        approval_task_line_model = rec.approval_template_id.approval_task_line_model
        if not approval_task_line_model:
            return None
        return self.env[approval_task_line_model].get_all_approval_task_line(
            transaction_model_name=rec.transaction_model_name,
            transaction_id=rec.transaction_id,
        )

    def get_next_approval_task_line(self):
        rec = self.ensure_approval_template()
        approval_task_line_model = rec.approval_template_id.approval_task_line_model
        if not approval_task_line_model:
            return None
        approval_task_line = self.env[approval_task_line_model]
        if have_method(approval_task_line, 'get_next_approval_task_line'):
            return self.env[approval_task_line_model].get_next_approval_task_line(
                transaction_model_name=rec.transaction_model_name,
                transaction_id=rec.transaction_id
            )
        else:
            return rec.approval_template_id.get_next_approval_task_line(
                approval_task_line, approval_instance=rec
            )

    def get_last_approval_task_line(self):
        rec = self.ensure_approval_template()
        approval_task_line_model = rec.approval_template_id.approval_task_line_model
        if not approval_task_line_model:
            return None
        return self.env[approval_task_line_model].get_last_approval_task_line(
            transaction_id=rec.transaction_id,
            transaction_model_name=rec.transaction_model_name,
        )

    def check_approval_task_status(self):
        # chek bila status masih didalam approval maka register ulang
        # bila satus sudah tidak dalam approval bisa di clear
        self.ensure_approval_template()
        transaction_object = self.get_transaction_object()
        if not transaction_object or not self.approval_template_id:
            self.env['approval.task'].search(
                [('approval_instance_id', '=', self.id)]
            ).approval_done()
            self.sudo().unlink()
            return

        if self.is_status_waiting_approval():
            self.register_approval_task_line(
                skip_send_notification=True, reset_reminder=False, reset_request_approval_task_date=False
            )
        else:
            self.unregister_approval_task_line()

    def register_approval_task_line(self, **kwargs):
        approval_task_line = (kwargs.get('approval_task_line_next') or kwargs.get('next_approval_task_line')
                              or kwargs.get('next_approval_transaction') or kwargs.get('approval_transaction')
                              or kwargs.get('approval_task_line') or self.get_next_approval_task_line())
        if self.env.context.get('__instance_register_approval_task_line'):
            return approval_task_line
        # if approval_task_line and approval_task_line.env.context.get('___register_approval_task_line'):
        #     return approval_task_line
        rec = self.with_context(__instance_register_approval_task_line=True)
        if 'notification_approval_id' not in kwargs:
            notification_approval = rec.get_notification_approval()
            notification_approval and kwargs.update(notification_approval_id=notification_approval.id)
        transaction_object = kwargs.get('transaction_object')
        if not isinstance(transaction_object, models.BaseModel):
            transaction_object = rec.get_transaction_object()
        company = getattr(transaction_object, "company_id")
        if company:
            rec.company_id = company
        rec.requester_id = rec.get_user_requestor()
        kwargs['approval_instance'] = rec
        kwargs['transaction_model_name'] = transaction_object._name
        kwargs['transaction_id'] = transaction_object.id
        kwargs['transaction_object'] = transaction_object
        kwargs['requester_id'] = rec.requester_id.id

        if rec.company_id:
            kwargs['company_id'] = rec.company_id.id
        if rec.name and 'name' not in kwargs:
            kwargs['name'] = rec.name
        if rec.document and 'document' not in kwargs:
            kwargs['document'] = rec.document
        if rec.description and 'description' not in kwargs:
            kwargs['description'] = rec.description

        if have_method(approval_task_line, "prepare_approval_task_dict"):
            update = safe_call_method(approval_task_line, "prepare_approval_task_dict", kwargs=kwargs)
            update and kwargs.update(update)
        if have_method(transaction_object, 'prepare_approval_task_dict'):
            update = safe_call_method(transaction_object, 'prepare_approval_task_dict', kwargs=kwargs)
            update and kwargs.update(update)
        transaction_id = kwargs.pop('transaction_id', None) or transaction_object.id
        transaction_model_name = kwargs.pop('transaction_model_name', None) or transaction_object._name
        approval_task = self.env['approval.task'].approval_setup(
            transaction_id, transaction_model_name, **kwargs
        )
        self.approval_task_id = approval_task
        return approval_task_line

    def unregister_approval_task_line(self, **kwargs):
        if not self:
            return
        rec = self.ensure_one()
        self.approval_task_id = False
        self.env['approval.task'].approval_done(
            transaction_id=rec.transaction_id,
            transaction_model_name=rec.transaction_model_name
        )

    def get_notification_approval(self):
        return self.approval_template_id.notification_approval_id

    def get_users_approval_notification(self, **kwargs):
        users = kwargs.get("users")
        if users:
            return users
        approval_task_lin = self.get_next_approval_task_line()
        if approval_task_lin:
            return approval_task_lin.get_users_for_notification(**kwargs)
        return self.env['res.users']

    def approval_action(self):
        approval_action = self.env.context.get('approval_action')

        if approval_action == 'request_approval':
            return self.action_request_approval()

        if approval_action == 'approve':
            return self.action_approve()

        if approval_action == 'reject':
            return self.action_reject()

        if approval_action == 'cancel':
            return self.action_cancel()

        if approval_action == 'reset_to_draft':
            return self.action_reset_to_draft()

        _logger.info("context %s ", self.env.context)

    def request_approval(self):
        approval_instance = self.ensure_one()
        approval_instance.ensure_approval_template()
        approval_template = approval_instance.approval_template_id
        if not approval_template:
            raise UserError("Template Approval not configure for this model")
        transaction_object = approval_instance.get_transaction_object()
        if not transaction_object:
            raise UserError("Transaction not Available")

        approval_template.invoke_method(
            transaction_object, 'validate_request_approval',
            dict(
                approval_instance=approval_instance,
                approval_template=approval_template,
            )
        )
        if approval_instance.pdf_sign not in [False, 'none']:
            # dry test
            pdf = approval_template.invoke_method(
                transaction_object, 'get_pdf_document',
                dict(
                    approval_instance=approval_instance,
                    approval_template=approval_template,
                ),
                raise_exceptions=True,
            )
            pdf_deep_link = pdf.get('pdf_deep_link')
            if pdf_deep_link and approval_instance.pdf_deep_link != pdf_deep_link:
                approval_instance.pdf_deep_link = pdf_deep_link

        config_approval_task_line = approval_template.get_config_instance(approval_instance) or {}
        if config_approval_task_line.get('auto_approved'):
            self.after_auto_approved(**config_approval_task_line)
            return

        if (
                config_approval_task_line.get('skip_create_approval_task_line')
                or config_approval_task_line.get('skip_create_approval_line')
        ):
            return

        approval_instance.configure_approval_task_line(**config_approval_task_line)
        approval_task_line = approval_instance.register_approval_task_line(**config_approval_task_line)
        approval_template.invoke_method(
            transaction_object,
            'approval_start',
            dict(
                approval_instance=approval_instance,
                approval_template=approval_template,
                approval_task_line=approval_task_line,
                approval_task_line_next=approval_task_line,
                next_approval_task_line=approval_task_line,
            ),
        )
        if approval_instance.pdf_sign not in [False, 'none']:
            approval_instance.submit_pdf_document(
                transaction_object=transaction_object,
                approval_instance=approval_instance,
                approval_template=approval_template,
                approval_task_line=approval_task_line,
            )
        if approval_task_line and not approval_instance.is_status_waiting_approval():
            _logger.warning("Status not waiting_approval try force set waiting_approval")
            approval_template.set_waiting_approval_status(transaction_object)

        return approval_task_line

    def configure_approval_task_line(self, **kwargs):
        without_clear_approval = kwargs.get('without_clear_approval')
        approval_template = kwargs.get('approval_template') or self.approval_template_id
        if not approval_template:
            raise UserError("Template Approval not configure for this model")
        transaction_object = kwargs.get('transaction_object')
        approval_clear = False
        ctx = dict(self.env.context)
        ctx['default_approval_instance_id'] = self.id
        ctx['default_transaction_id'] = transaction_object.id
        ctx['default_transaction_model_name'] = transaction_object._name
        approval_line = kwargs.get('approval_line') or approval_template.get_approval_line_from_matrix(**kwargs)

        if not approval_line:
            creator = kwargs.get('creator_approval_task_line')
            method_create_approval_task_line = kwargs.get('method_create_approval_task_line')
            _logger.info("creator %s , method_create_approval_task_line %s ", creator, method_create_approval_task_line)
            if creator and isinstance(creator, str):
                creator = self.env[creator].browse()
                _logger.info("creator %s ", creator)
            if isinstance(creator, models.BaseModel):
                if not method_create_approval_task_line:
                    method_create_approval_task_line = "create_approval_task_line"
            if not isinstance(creator, models.BaseModel) or (
                    isinstance(method_create_approval_task_line, str)
                    and not have_method(creator, method_create_approval_task_line)
            ):
                creator = transaction_object
                _logger.info("using transaction_object %s , %s ", creator, method_create_approval_task_line)
                if isinstance(
                        method_create_approval_task_line, str
                ) and not have_method(creator, method_create_approval_task_line):
                    raise UserError("Method %s not found" % method_create_approval_task_line)

            if not without_clear_approval and kwargs.get('clear_approval', False):
                approval_clear = True
                self.clear_approval()

            _logger.info("invoke creator %s : %s ", creator, method_create_approval_task_line)
            approval_line = safe_call_method(
                creator.with_context(ctx),
                method_create_approval_task_line,
                kwargs=kwargs,
            )
            _logger.info("approval_line %s , %s ", creator, approval_line)
            if isinstance(approval_line, models.BaseModel):
                return approval_line

        if not approval_line:
            approval_record = None
            if approval_template.type_approval_default == 'multi_user':
                approval_record = approval_template.users_approval_default_ids
            elif approval_template.type_approval_default == 'multi_group':
                approval_record = approval_template.groups_approval_default_ids
            else:
                _logger.warning("No Approval %s.", approval_template.type_approval_default)
            if approval_record:
                approval_line = [approval_record]

        if not approval_line:
            raise UserError("Approval Line not Available")

        if isinstance(approval_line, dict):
            model = approval_line['model'] or approval_template.approval_task_line_model
            approval_task_line = approval_line['approval_task']
        else:
            model = approval_template.approval_task_line_model
            approval_task_line = approval_line

        if not without_clear_approval and not approval_clear:
            self.clear_approval()

        return self.env[model].with_context(ctx).create_approval_task_line(approval_task_line, **kwargs)

    def get_transaction_currency(self, transaction_object):
        if hasattr(transaction_object, "currency_id"):
            return transaction_object.currency_id or self.env.company.currency_id
        else:
            return self.env.company.currency_id

    def get_transaction_requester(self, transaction_object, transaction_requester_id):
        return self.env['res.users'].browse(transaction_requester_id or self.env.context.get(
            'default_requester_id') or transaction_object.create_uid.id or self.env.user.id)

    def _prepare_approval_task_line(self, **config):
        raise NotImplemented

    def action_request_approval(self):
        return self.request_approval()

    def action_register_approval_task_line(self):
        self.register_approval_task_line()

    @api.model
    def redirect_window_action(self, window_action, context):
        from odoo.tools.safe_eval import safe_eval
        action = window_action.read()[0]
        if action.get('context'):
            if isinstance(action['context'], str):
                ctx = safe_eval(action['context'])
            else:
                ctx = dict(action['context'])
            ctx.update(context)
        else:
            ctx = context
        action['context'] = ctx
        return action

    def get_context_action(self, check_approval):
        context = dict(self.env.context)
        transaction_object = self.get_transaction_object()
        if transaction_object and isinstance(transaction_object, models.Model):
            model_name = transaction_object._name
            model_res_id = transaction_object.id
        else:
            model_name = self._name
            model_res_id = self.id
        if isinstance(check_approval, models.Model):
            context.update({
                'approval_task_line_id': check_approval.id,
                'approval_task_line_model': check_approval._name,
            })
        context.update({
            'active_model': model_name,
            'active_id': model_res_id,
            'approval_instance_model': self._name,
            'approval_instance_res_id': self.id,
        })

        _logger.info(" model_name %s , model_res_id %s ", model_name, model_res_id)
        return context

    def action_approve(self):

        check_approval = self.get_next_approval_task_line()
        self.ensure_approval_template()
        approval_template = self.approval_template_id
        approve_action_type = approval_template.approve_action_type
        if approve_action_type in ['window_action', 'server_action']:
            if approve_action_type == 'window_action' and approval_template.approve_window_action_id:
                return self.redirect_window_action(
                    approval_template.approve_window_action_id,
                    self.get_context_action(check_approval)
                )
            if approve_action_type == 'server_action' and approval_template.approve_server_action_id:
                return approval_template.approve_server_action_id.with_context(
                    self.get_context_action(check_approval),
                ).run()

        transaction_object = self.get_transaction_object()
        return self.do_approve(
            approval_instance=self,
            approval_task_line=check_approval,
            approval_template=approval_template,
            transaction_object=transaction_object
        )

    def action_reject(self):
        check_approval = self.get_next_approval_task_line()
        self.ensure_approval_template()
        approval_template = self.approval_template_id
        action_type = approval_template.reject_action_type
        if action_type in ['window_action', 'server_action']:
            if action_type == 'window_action' and approval_template.reject_window_action_id:
                return self.redirect_window_action(
                    approval_template.reject_window_action_id,
                    self.get_context_action(check_approval)
                )
            if action_type == 'server_action' and approval_template.reject_server_action_id:
                return approval_template.reject_server_action_id.with_context(
                    self.get_context_action(check_approval),
                ).run()

        # if have_method(check_approval, 'action_reject'):
        #     return safe_call_method(check_approval, 'action_reject', kwargs=kwargs)
        return self.do_reject()
        # return {
        #     'name': 'Reject Message',
        #     'type': 'ir.actions.act_window',
        #     'view_mode': 'form',
        #     'res_model': 'popup.reject.message.wizard',
        #     'target': 'new',
        #     'context': context,
        # }

    def action_cancel(self):
        self.ensure_approval_template()
        approval_template = self.approval_template_id
        approve_action_type = approval_template.approve_action_type
        if approve_action_type in ['window_action', 'server_action']:
            if approve_action_type == 'window_action' and approval_template.approve_window_action_id:
                return self.redirect_window_action(
                    approval_template.approve_window_action_id,
                    self.get_context_action(None)
                )
            if approve_action_type == 'server_action' and approval_template.approve_server_action_id:
                return approval_template.approve_server_action_id.with_context(
                    self.get_context_action(None),
                ).run()

        transaction_object = self.get_transaction_object()
        return self.do_cancel(
            approval_instance=self,
            approval_template=approval_template,
            transaction_object=transaction_object
        )

    def action_reset_to_draft(self):
        approval_instance = self.ensure_one()
        approval_instance.ensure_approval_template()
        approval_template = approval_instance.approval_template_id
        if not approval_template:
            raise UserError("Template Approval not configure for this model")
        transaction_object = approval_instance.get_transaction_object()
        if not transaction_object:
            raise UserError("Transaction not Available")
        approval_template.invoke_method(
            transaction_object, 'validate_reset_to_draft',
            dict(
                approval_instance=approval_instance,
                approval_template=approval_template,
                transaction_object=transaction_object,
            )
        )
        approval_template = self.approval_template_id
        action_type = approval_template.reject_action_type
        if action_type in ['window_action', 'server_action']:
            if action_type == 'window_action' and approval_template.reset_to_draft_window_action_id:
                return self.redirect_window_action(
                    approval_template.reset_to_draft_window_action_id,
                    self.get_context_action(None)
                )
            if action_type == 'server_action' and approval_template.reset_to_draft_server_action_id:
                return approval_template.reset_to_draft_server_action_id.with_context(
                    self.get_context_action(None),
                ).run()

        # if have_method(check_approval, 'action_reject'):
        #     return safe_call_method(check_approval, 'action_reject', kwargs=kwargs)
        return self.do_reset_to_draft(
            approval_instance=approval_instance,
            approval_template=approval_template,
            transaction_object=transaction_object,
        )

    def do_reset_to_draft(self, **kwargs):
        approval_instance = self.ensure_one()
        approval_template = approval_instance.approval_template_id
        kwargs.setdefault('approval_instance', approval_instance)
        return approval_template.do_reset_to_draft(**kwargs)

    def action_clear_approval(self):
        self.clear_approval()

    def approve(self, **kwargs):
        return self.do_approve(**kwargs)

    def do_approve(self, **kwargs):
        rec = self.ensure_one()
        approval_template = self.approval_template_id
        check_approval = rec.get_next_approval_task_line()
        kw = dict(kwargs)
        kw.setdefault('approval_instance', self)
        kw.setdefault('approval_template', approval_template)
        kw.setdefault('transaction_object', rec.get_transaction_object())
        kw.setdefault('approval_task_line', check_approval)
        return approval_template.do_approve(**kw)

    def before_approve(self, **kwargs):
        if self:
            self.approval_template_id.before_approve(**kwargs)
        else:
            _logger.warning("No Instance for Before Approve")

        return self

        # approval_instance = self.ensure_one()
        # kw = dict(kwargs)
        # kw['approval_instance'] = approval_instance
        # transaction_object = approval_instance.get_transaction_object()
        # approval_instance.ensure_approval_template()
        # approval_template = approval_instance.approval_template_id
        # approval_template.invoke_method(transaction_object, 'before_approve', kw)
        # return approval_instance

    def after_approve(self, **kwargs):
        if self:
            self.approval_template_id.after_approve(**kwargs)
        else:
            _logger.warning("No Instance for After Approve")

        return self

        # approval_instance = self.ensure_one()
        # approval_instance.ensure_approval_template()
        # approval_template = approval_instance.approval_template_id
        # notification_template = approval_template.notification_approved_id
        #
        # kw = dict(kwargs)
        # kw['skip_send_notification'] = True
        # kw['approval_instance'] = approval_instance
        # kw['approval_template'] = approval_template
        # kw['notification_template'] = notification_template
        # transaction_object = approval_instance.get_transaction_object()
        # is_approval_done = kwargs.get('is_approval_done')
        # trx_update_value = kwargs.get('transaction_update_value') or {}
        #
        # approval_template.invoke_method(transaction_object, 'after_approve', kw)
        #
        # if is_approval_done:
        #     kw['is_approved'] = True
        #     trx_update_value.update(kwargs.get('update_value') or {})
        #     state_field = approval_template.get_state_field()
        #     state_approved = approval_template.get_state_approved()
        #     if state_approved and state_field not in trx_update_value:
        #         trx_update_value[state_field] = state_approved
        #
        # if trx_update_value:
        #     _logger.info("Info Update state %s ", trx_update_value)
        #     transaction_object.write(trx_update_value)
        # elif is_approval_done:
        #     _logger.warning("No Update state when is_approval_done")
        #
        # if not approval_instance.is_status_waiting_approval() or is_approval_done:
        #     kw['is_approval_done'] = True
        #     kw['is_approved'] = True
        #     approval_instance.done_approval(**kw)
        # else:
        #     kw['is_approval_done'] = False
        #     kw['skip_send_notification'] = False
        #     kw['request_approval_task_date'] = fields.Datetime.now()
        #     approval_instance.register_approval_task_line(**kw)
        #
        # kw_approved = dict(kwargs)
        # kw_approved.update(
        #     approval_template=approval_template,
        #     approval_instance=approval_instance,
        #     transaction_id=approval_instance.transaction_id,
        #     transaction_model_name=approval_instance.transaction_model_name,
        # )
        #
        # notes_chatter = False
        # notification = self.notification_approved_id
        # if notification:
        #     requestor = self.get_user_requestor()
        #     notification.send_notification_to_users(requestor, transaction_object.id, **kwargs)
        #     notes_chatter = notification.notes_chatter
        #
        # if not notes_chatter and self.notes_chatter_approved:
        #     if have_method(transaction_object, 'get_approved_message'):
        #         approved_message = safe_call_method(
        #             transaction_object, "get_approved_message", kwargs=kw_approved
        #         )
        #     else:
        #         approved_message = self.get_approved_message(**kw)
        #     approved_message and self._mail_message_approve(approved_message)
        #
        # return approval_instance

    def after_auto_approved(self, **kwargs):
        if not self:
            _logger.warning("No Instance for After Approve")
            return self

        approval_instance = self.ensure_one()
        approval_instance.ensure_approval_template()
        approval_template = approval_instance.approval_template_id
        notification_template = approval_template.notification_approved_id
        kw = dict(kwargs)
        kw['skip_send_notification'] = True
        kw['approval_instance'] = approval_instance
        kw['approval_template'] = approval_template
        kw['notification_template'] = notification_template
        kw['is_approved'] = True
        kw['is_approval_done'] = True
        transaction_object = approval_instance.get_transaction_object()
        approval_template.invoke_method(transaction_object, 'after_approve', kw)
        trx_update_value = kwargs.get('transaction_update_value') or {}
        trx_update_value.update(kwargs.get('update_value') or {})
        state_field = approval_instance.get_state_field()
        state_approved = approval_instance.get_state_approved()
        if state_approved and state_field not in trx_update_value:
            trx_update_value[state_field] = state_approved

        if trx_update_value:
            _logger.info("Info Update state %s ", str(trx_update_value))
            transaction_object.write(trx_update_value)
        else:
            _logger.warning("No Update state when is_approval_done")
        approval_instance.done_approval(**kw)
        if approval_template.notes_chatter_approved:
            if have_method(transaction_object, 'get_approved_message'):
                approved_message = safe_call_method(transaction_object, 'get_approved_message', kwargs=kw)
            else:
                approved_message = self.get_approved_message(**kw)
            approved_message and self._mail_message_approve(approved_message)

    def get_approved_message(self, **kwargs):
        return _("%s has approved this request") % (self.env.user.name)

    def reject(self, reason=None, **kwargs):
        return self.do_reject(reason=reason, **kwargs)

    def do_reject(self, **kw):
        approval_instance = self.ensure_one()
        approval_instance.ensure_approval_template()
        approval_template = approval_instance.approval_template_id
        reject_approval = approval_instance.get_next_approval_task_line()
        kw.setdefault('approval_instance', approval_instance)
        kw.setdefault('approval_task_line', reject_approval)
        return approval_template.do_reject(**kw)

    def do_cancel(self, **kw):
        approval_instance = self.ensure_one()
        approval_instance.ensure_approval_template()
        approval_template = approval_instance.approval_template_id
        kw.setdefault('approval_instance', approval_instance)
        return approval_template.do_cancel(kw)

    def do_set_to_draft(self, **kw):
        approval_instance = self.ensure_one()
        approval_instance.ensure_approval_template()
        approval_template = approval_instance.approval_template_id
        kw.setdefault('approval_instance', approval_instance)
        return approval_template.do_set_to_draft(kw)

    def reject_from_popup_reject(self, **kwargs):
        return self.do_reject(**kwargs)

    def before_reject(self, **kwargs):
        if not self:
            _logger.warning("No Instance for Before Reject")
            return self
        approval_instance = self.ensure_one()
        approval_instance.ensure_approval_template()
        approval_template = approval_instance.approval_template_id
        kw = dict(kwargs)
        kw['approval_instance'] = approval_instance
        transaction_object = approval_instance.get_transaction_object()
        approval_template.invoke_method(transaction_object, 'before_reject', kw)
        return approval_instance

    def after_reject(self, **kwargs):
        if not self:
            _logger.warning("No Instance for After Reject")
            return self
        approval_instance = self.ensure_one()
        approval_instance.ensure_approval_template()
        approval_template = approval_instance.approval_template_id
        notification_template = approval_template.notification_approved_id

        kw = dict(kwargs)
        kw['approval_instance'] = approval_instance
        kw['approval_template'] = approval_template
        kw['notification_template'] = notification_template
        transaction_object = approval_instance.get_transaction_object()
        is_approval_done = kwargs.get('is_approval_done')
        trx_update_value = kwargs.get('transaction_update_value') or {}

        approval_template.invoke_method(transaction_object, 'after_reject', kw)
        approval_task_line = kwargs.get('approval_task_line') or kwargs.get('approval_transaction')
        if is_approval_done:
            kw['is_rejected'] = True
            trx_update_value.update(kwargs.get('update_value') or {})
            state_field = approval_instance.get_state_field()
            state_rejected = approval_instance.get_state_rejected()
            if state_rejected and state_field not in trx_update_value:
                trx_update_value[state_field] = state_rejected

        if trx_update_value:
            transaction_object.write(trx_update_value)
            _logger.info("No update state %s", trx_update_value)
        elif is_approval_done:
            _logger.warning("No update state")

        if not approval_instance.is_status_waiting_approval() or is_approval_done:
            kw['is_approval_done'] = True
            kw['is_rejected'] = True
            approval_instance.done_approval(**kw)
        else:
            kw['is_approval_done'] = False
            kw['skip_send_notification'] = False
            kw['request_approval_task_date'] = fields.Datetime.now()
            approval_instance.register_approval_task_line(**kw)

        kw_rejected = dict(kwargs)
        kw_rejected.update(
            approval_template=approval_template,
            approval_instance=approval_instance,
            transaction_id=approval_instance.transaction_id,
            transaction_model_name=approval_instance.transaction_model_name,
        )
        if approval_template.notes_chatter_rejected:
            if have_method(transaction_object, 'get_rejected_message'):
                rejected_message = safe_call_method(
                    transaction_object, "get_rejected_message", kwargs=kw_rejected
                )
            else:
                rejected_message = self.get_rejected_message(**kw)
            rejected_message and self._mail_message_approve(rejected_message)
        approval_task_line.send_rejected_notification(**kw_rejected)

        return approval_instance

    @api.model
    def get_rejected_message(self, **kwargs):
        reason = kwargs.get('reason')
        return _('Note Reject => %s') % reason

    def cancel(self, reason):

        pass

    def done_approval(self, **kwargs):
        if not self:
            _logger.warning("No Instance for done Approval")
            return self
        approval_instance = self.ensure_one()
        approval_instance.ensure_approval_template()
        approval_template = approval_instance.approval_template_id
        approval_template.done_approval(**kwargs)
        # kw = dict(kwargs)
        # kw['approval_instance'] = approval_instance
        # transaction_object = approval_instance.get_transaction_object()
        # safe_call_method(transaction_object, approval_template.invoke_approval_done, kwargs=kw)
        # self.unregister_approval_task_line()
        # if approval_instance.is_status_waiting_approval():
        #     if kwargs.get('is_approved'):
        #         _logger.warning("Status is waiting_approval try force set done")
        #         approval_template.set_approved_status(transaction_object)

    def clear_approval(self):
        if not self:
            _logger.warning("No Instance for celar Approval")
            return self
        rec = self.ensure_one()
        approval_task_line_model = rec.approval_template_id.approval_task_line_model
        self.env[approval_task_line_model].search([
            ('transaction_model_name', '=', rec.transaction_model_name),
            ('transaction_id', '=', rec.transaction_id),
        ]).unlink()
        self.unregister_approval_task_line()

    def _mail_message_approve(self, message):
        self.env['mail.message'].sudo().create({
            'model': self.transaction_model_name,
            'res_id': self.transaction_id,
            'message_type': 'comment',
            'author_id': self.env.user.partner_id.id,
            'date': datetime.now(),
            'body': message,
        })

    def submit_pdf_document(self, **kwargs):
        raise NotImplemented("submit_pdf_document Not ready to integrate.")

    def sign_pdf_document(self, **kwargs):
        raise NotImplemented("sign_pdf_document Not ready to integrate.")

    def cancel_pdf_document(self, **kwargs):
        raise NotImplemented("cancel_pdf_document Not ready to integrate.")


class ApprovalInstance(models.Model):
    _name = 'approval.instance'
    _inherit = 'approval.instance.mixin'

    approval_template_id = fields.Many2one('approval.template', compute='_compute_approval_template_id')
    approval_task_line_model = fields.Char(related='approval_template_id.approval_task_line_model')
    approval_task_line = fields.One2many('approval.task.line', 'approval_instance_id', string='Approval Task Lines')
    approval_audit_log_ids = fields.Many2many('approval.audit.log', compute="_compute_approval_audit_log_ids")
    user_ids = fields.Many2many('res.users', compute='_compute_approval_users_groups', compute_sudo=True)
    group_ids = fields.Many2many('res.groups', compute='_compute_approval_users_groups', compute_sudo=True)
    @api.depends('model_id', 'model', 'transaction_model_name')
    def _compute_approval_template_id(self):
        for rec in self:
            rec.approval_template_id = self.approval_template_id.search_template_by_model(
                rec.transaction_model_name or rec.model
            )

    def _compute_approval_audit_log_ids(self):
        for rec in self:
            rec.approval_audit_log_ids = self.approval_audit_log_ids.search(
                [('transaction_id', '=', rec.transaction_id), ('transaction_id', '=', rec.transaction_id)],
                order='id desc',
            )

    def _compute_approval_users_groups(self):
        for rec in self:
            next_approval_task_line = rec.get_next_approval_task_line()
            user_ids = self.user_ids.browse()
            group_ids = self.group_ids.browse()
            if next_approval_task_line:
                if have_method(next_approval_task_line, 'get_users_for_approval'):
                    user_ids = next_approval_task_line.get_users_for_approval()
                elif have_method(next_approval_task_line, 'get_users'):
                    user_ids = next_approval_task_line.get_users()
                if have_method(next_approval_task_line, 'get_groups'):
                    group_ids = next_approval_task_line.get_groups()
            rec.user_ids = user_ids.ids if user_ids else False
            rec.group_ids = group_ids.ids if group_ids else False
