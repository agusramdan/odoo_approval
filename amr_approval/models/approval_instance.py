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
    pdf_sign_server = fields.Selection([('local', 'Local'), ('remote', 'Remote')], default='local')
    pdf_sign = fields.Selection(
        [('none', 'None'),
         ('approve_is_sign_pdf', 'Approve is Sign PDF'),
         ('approve_form_sign_pdf', 'Sign PDF is Approve'),
         ], default='none', help="""
            none : Not related pdf
            Approve to sign: When approve this instance will propagate to sign pdf.
            Approve from : Sign document will approve this instance when approve will redirect to sign authenticate.
            """
    )
    pdf_deep_link = fields.Char(store=False)
    pdf_file = fields.Binary('PDF File', store=False)
    pdf_filename = fields.Char('PDF Filename', store=False)
    pdf_hash = fields.Char('PDF Hash', store=False)

    pdf_lock_file = fields.Binary('Lock Lock', store=False)
    pdf_lock_filename = fields.Char('Lock Filename', store=False)
    pdf_lock_hash = fields.Char('Lock Hash', store=False)
    pre_signed_pdf = fields.Binary('Pre Signed PDF', store=False)
    pre_signed_qr = fields.Char(store=False)

    signed_pdf = fields.Binary('Signed PDF', store=False)
    signed_pdf_filename = fields.Char('Signed PDF Filename', store=False)

    approval_document_id = fields.Many2one('approval.document', ondelete='set null', )
    approval_template_id = fields.Many2one('approval.template', ondelete='set null', )
    approval_template_line_id = fields.Many2one('approval.template.line', ondelete='set null', )
    approval_task_id = fields.Many2one('approval.task', ondelete='set null', )

    flag_reject = fields.Boolean()
    note_reject = fields.Text()
    flag_reset_to_draft = fields.Boolean()
    note_reset_to_draft = fields.Text()

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
    # for generic notification template
    notification_to_user_id = fields.Many2one(
        'res.users', string='Notification to User',
        compute="_compute_notification_to_user_id", compute_sudo=True,
        help="User who will receive the notification.",
    )
    notification_to_partner_id = fields.Many2one(
        'res.partner', string='Notification to User/Partner',
        compute="_compute_notification_to_user_id", compute_sudo=True,
        help="User who will receive the notification.",
    )

    # approval_task_id = fields.Many2many(
    #     'approval.task',
    #     string='Approval Task',
    #     compute='_compute_approval_task',
    #     compute_sudo=True,
    # )
    def get_internal_number(self):
        if self:
            transaction_object = self.get_transaction_object()
            return (
                    self.approval_document_id.get_internal_number(transaction_object) or
                    getattr(transaction_object, 'name', None) or transaction_object.display_name or self.name
            )
        return None

    def get_internal_document(self):
        if self:
            transaction_object = self.get_transaction_object()
            return (
                    self.approval_document_id.get_internal_document(transaction_object) or
                    self.approval_template_id.document or
                    getattr(transaction_object, '_description', None) or self.document
            )
        return None

    def get_internal_description(self):
        if self:
            transaction_object = self.get_transaction_object()
            return (
                    self.approval_document_id.get_internal_description(transaction_object) or
                    self.approval_template_id.description or
                    getattr(transaction_object, '_description', None) or self.description
            )
        return None

    def get_internal_requestor(self):
        if self:
            transaction_object = self.get_transaction_object()
            return (
                    self.approval_document_id.get_internal_requestor(transaction_object) or self.requester_id
            )
        return self.env['res.users'].browse()

    def get_internal_reject_reason(self):
        return self.note_reject or self.env.context.get('reject_reason')

    def get_internal_reset_to_draft_reason(self):
        return self.note_reset_to_draft or self.env.context.get('reset_to_draft_reason')

    def get_internal_approver(self):
        user_execution = self.env.context.get('user_execution')
        if isinstance(user_execution, models.Model):
            return user_execution
        _logger.info('user_execution %s ',user_execution)
        return self.env.user

    def get_internal_url(self):
        if self.url:
            return self.url
        transaction_object = self.get_transaction_object()
        if have_method(transaction_object, 'get_internal_url'):
            return transaction_object.get_internal_url()
        return ""

    @api.depends_context('notification_to_user')
    def _compute_notification_to_user_id(self):
        for rec in self:
            notification_to_user = self.env.context.get('notification_to_user', False)
            if notification_to_user:
                rec.notification_to_user_id = notification_to_user.id
                rec.notification_to_partner_id = notification_to_user.partner_id.id
            else:
                rec.notification_to_user_id = False
                rec.notification_to_partner_id = False

    @api.model
    def ensure_disable_auto_register(self, transaction_object):
        if transaction_object and not transaction_object.env.context.get('__skip_approval_transaction_status'):
            transaction_object = transaction_object.with_context(
                __skip_approval_transaction_status=True
            )
        return transaction_object

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
        if not self:
            return False
        return self.approval_template_id and self.approval_template_id.get_state_waiting_approvals()

    def get_state_field(self):
        if not self:
            return False
        return self.approval_template_id.get_state_field()

    def get_state_rejected(self):
        if not self:
            return False
        return self.approval_template_id.get_state_rejected()

    def get_state_approved(self):
        if not self:
            return False
        return self.approval_template_id.get_state_approved()

    def get_transaction_status(self, transaction=None):
        if not self:
            return False
        rec = self.ensure_one()
        transaction = transaction or rec.get_transaction_object()
        return self.approval_template_id and self.approval_template_id.get_transaction_status(transaction)

    def get_user_requestor(self, transaction=None):
        if not self:
            return False
        rec = self.ensure_one()
        transaction = transaction or rec.get_transaction_object()
        return self.approval_template_id.get_user_requestor(transaction)

    def is_model_need_approval(self, transaction=None):
        if not self:
            return False
        rec = self.ensure_one()
        transaction = transaction or rec.get_transaction_object()
        return self.approval_template_id and self.approval_template_id.is_model_need_approval(transaction)

    def is_status_request_approval(self, transaction=None):
        if not self:
            return False
        rec = self.ensure_one()
        transaction = transaction or rec.get_transaction_object()
        return self.approval_template_id and self.approval_template_id.is_status_request_approval(transaction)

    def is_status_waiting_approval(self, transaction=None):
        if not self:
            return False
        rec = self.ensure_one()
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

        approval_instance = (
                self.get_instance_for_transaction(transaction_model_name, transaction_id) or
                self.create([{
                    'approval_template_id': approval_template_id.id,
                    'transaction_model_name': transaction_model_name,
                    'transaction_id': transaction_id,
                }])[0]
        )
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
        return rec.approval_template_id.get_all_approval_task_line(
            approval_instance=rec
        )

    def get_next_approval_task_line(self):
        rec = self.ensure_approval_template()
        return rec.approval_template_id.get_next_approval_task_line(
            approval_instance=rec
        )

    def get_last_approval_task_line(self):
        rec = self.ensure_approval_template()
        return rec.approval_template_id.get_last_approval_task_line(
            approval_instance=rec
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
        kwargs['transaction_object'] = transaction_object = self.ensure_disable_auto_register(transaction_object)
        rec.company_id = getattr(transaction_object, "company_id", None)
        rec.requester_id = rec.get_user_requestor()
        kwargs['approval_instance'] = rec
        kwargs['transaction_model_name'] = transaction_object._name
        kwargs['transaction_id'] = transaction_object.id
        kwargs['transaction_object'] = transaction_object
        kwargs.pop('approval_action', None)
        kwargs = self._prepare_action(**kwargs)
        approval_document = kwargs.get('approval_document')
        if approval_document and approval_document.requestor_group_ids:
            if not rec.requester_id.user_has_any_group(approval_document.requestor_group_ids):
                raise UserError(
                    "Requester not alaw create request approval for this document %s . " % approval_document.display_name)
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
        self.document = approval_task.document
        self.name = approval_task.name
        self.url = approval_task.url
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

        if approval_action == 'show_sign_pdf':
            return self.action_show_sign_pdf()

        _logger.info("context %s ", self.env.context)

    def request_approval(self):
        kwargs = {}
        kwargs['approval_instance'] = approval_instance = self.ensure_one()
        transaction_object = approval_instance.get_transaction_object()
        if not transaction_object:
            raise UserError("Transaction not Available")
        kwargs['transaction_object'] = transaction_object = self.ensure_disable_auto_register(transaction_object)
        kwargs['approval_template'] = approval_template = self.approval_template_id
        kwargs['approval_document'] = approval_document = self.approval_document_id.get_approval_document(
            transaction_object
        )
        if not approval_template:
            raise UserError("Template Approval not configure for this model")

        approval_template.invoke_method(
            transaction_object, 'validate_request_approval', kwargs
        )
        approval_template_line = None
        if approval_document:
            approval_instance.pdf_sign = approval_document.pdf_sign
            approval_instance.pdf_sign_server = approval_document.pdf_sign_server
            approval_instance.approval_document_id = approval_document
            approval_template_line = approval_instance.approval_template_line_id
        else:
            approval_instance.approval_document_id = False
            approval_instance.pdf_sign = False

        if not approval_template_line:
            approval_template_line = approval_template.approval_template_line_id
        approval_instance.approval_template_line_id = approval_template_line
        kwargs['approval_template_line'] = approval_template_line
        config_approval_task_line = approval_template.get_config_instance(approval_instance) or {}
        if config_approval_task_line.get('auto_approved'):
            self.after_auto_approved(**config_approval_task_line)
            return

        if (
                config_approval_task_line.get('skip_create_approval_task_line')
                or config_approval_task_line.get('skip_create_approval_line')
        ):
            return self.do_approval_start(**kwargs)

        approval_instance.configure_approval_task_line(**config_approval_task_line)
        kwargs['approval_task_line'] = approval_instance.register_approval_task_line(**config_approval_task_line)
        return self.do_approval_start(**kwargs)

    def do_approval_start(self, **kwargs):
        approval_instance = kwargs.get('approval_instance') or self.ensure_one()
        approval_template = kwargs.get('approval_template') or approval_instance.approval_template_id
        transaction_object = kwargs.get('transaction_object') or approval_instance.get_transaction_object()
        kwargs['transaction_object'] = transaction_object = self.ensure_disable_auto_register(transaction_object)
        approval_task_line = kwargs.get('approval_task_line') or approval_instance.get_next_approval_task_line()
        if transaction_object and not transaction_object.env.context.get('__skip_approval_transaction_status'):
            transaction_object = kwargs['transaction_object'] = transaction_object.with_context(
                __skip_approval_transaction_status=True
            )
        approval_template.invoke_method(transaction_object, 'approval_start', kwargs)
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

        approval_template_line = approval_template.approval_template_line_id.get_approval_template_line(**kwargs)
        if approval_template_line:
            _logger.info("Pake approval_template_line %s ", approval_template_line)
            approval_task_lines = approval_template_line.create_approval_task_line(approval_task_line, **kwargs)
            approval_template_line.setup_reject_to_rule_line(approval_task_lines, **kwargs)
            return approval_task_lines
        else:
            _logger.info("Tidak punya approval_template_line")
            return self.env[model].with_context(ctx).create(approval_task_line)

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

    def _prepare_action(self, approval_action=None, **kw):

        approval_instance = kw.get('approval_instance') or self.ensure_one()
        kw.setdefault('approval_instance', approval_instance)

        date_execution = kw.get('date_execution') or fields.Datetime.now()
        kw.setdefault('date_execution', date_execution)

        user_execution = kw.get('user_execution') or self.env.user
        kw.setdefault('user_execution', user_execution)

        transaction_id = kw.get('transaction_id') or approval_instance.transaction_id
        kw.setdefault('transaction_id', transaction_id)

        transaction_model_name = kw.get('transaction_model_name') or approval_instance.transaction_model_name
        kw.setdefault('transaction_model_name', transaction_model_name)

        approval_template = kw.get('approval_template') or approval_instance.approval_template_id
        kw.setdefault('approval_template', approval_template)

        transaction_object = kw.get('transaction_object') or approval_instance.get_transaction_object()
        kw.setdefault('transaction_object', transaction_object)

        approval_document = (
                kw.get('approval_document') or
                approval_instance.approval_document_id or
                approval_instance.approval_document_id.get_approval_document(transaction_object)
        )
        kw.setdefault('approval_document', approval_document)

        approval_template_line = (
                kw.get('approval_template_line') or
                approval_instance.approval_template_line_id or
                approval_document.approval_template_line_id or
                approval_template.approval_template_line_id
        )
        kw.setdefault('approval_template_line', approval_template_line)

        approval_task_line = (
                kw.get('approval_task_line', None) or
                approval_template_line.get_next_approval_task_line(**kw)
        )
        kw.setdefault('approval_task_line', approval_task_line)

        if approval_action:
            approval_action_context = dict(
                __prepared_approval_action=True,
                user_execution=user_execution,
                date_execution=date_execution,
            )
            approval_task = (
                    kw.get('approval_task') or
                    approval_instance.approval_task_id or
                    approval_instance.approval_task_id.get_approval_task(
                        transaction_id, transaction_model_name
                    )
            )
            kw.setdefault('approval_task', approval_task)
            if not approval_task_line:
                if approval_template_line:
                    approval_task_line = approval_template_line.get_next_approval_task_line(**kw)
                else:
                    _logger.info("Without approval_template_line.")
                    approval_task_line = approval_instance.get_next_approval_task_line()

            if (
                    approval_template_line and approval_task_line and
                    approval_action in ['approver_action', 'approve', 'reject']
            ):
                result = approval_template_line.check_action_right(approval_task_line, kw) or {}
                kw.update(result)
                approval_action_context.update(result)
                if result.get('execution_method') == 'with_user':
                    user_approver = result.get('user_approver')
                    transaction_object = transaction_object.with_user(user_approver)
                    approval_task_line = approval_task_line.with_user(user_approver)
                if result.get('execution_method') == 'sudo':
                    transaction_object = transaction_object.sudo()
                    approval_task_line = approval_task_line.sudo()
                _logger.info("approval_template_line.check_action_right %s", result)

            if approval_action in ['requester_action', 'rest_to_draft', 'cancel']:
                result = approval_template.check_requester_action_right(**kw)
                kw.update(result)
                if result.get('execution_method') == 'with_user':
                    user_approver = result.get('user_approver')
                    transaction_object = transaction_object.with_user(user_approver)
                    approval_task_line = approval_task_line.with_user(user_approver)
                if result.get('execution_method') == 'sudo':
                    transaction_object = transaction_object.sudo()
                    approval_task_line = approval_task_line.sudo()

            if not approval_instance.env.context.get('__prepared_approval_action'):
                ctx = dict(approval_instance.env.context)
                ctx.update(approval_action_context)
                kw['approval_instance'] = approval_instance.with_context(ctx)

            if not approval_template.env.context.get('__prepared_approval_action'):
                ctx = dict(approval_template.env.context)
                ctx.update(approval_action_context)
                kw['approval_template'] = approval_template.with_context(ctx)

            if not approval_document.env.context.get('__prepared_approval_action'):
                ctx = dict(approval_document.env.context)
                ctx.update(approval_action_context)
                kw['approval_document'] = approval_document.with_context(ctx)

            if not transaction_object.env.context.get('__prepared_approval_action'):
                ctx = dict(transaction_object.env.context)
                ctx.update(approval_action_context)
                kw['transaction_object'] = transaction_object.with_context(ctx)

            if approval_template_line and not approval_template_line.env.context.get('__prepared_approval_action'):
                ctx = dict(approval_template_line.env.context)
                ctx.update(approval_action_context)
                kw['approval_template_line'] = approval_template_line.with_context(ctx)

            if approval_task_line and not approval_task_line.env.context.get('__prepared_approval_action'):
                ctx = dict(approval_task_line.env.context)
                ctx.update(approval_action_context)
                kw['approval_task_line'] = approval_task_line.with_context(ctx)
        else:
            _logger.info("_prepare_action approval_action %s", approval_action)
        _logger.info("_prepare_action %s", kw)
        return kw

    def action_approve(self):
        kw = self._prepare_action(approval_action='approve')
        approval_template = kw.get('approval_template')
        transaction_object = kw.get('transaction_object')
        approval_template.invoke_method(
            transaction_object, 'validate_approve', kw
        )
        # approval_template_line.check_action_right(approval_task_line, {})
        if approval_template.approve_action_type:
            return approval_template.approval_action_custom('approve', **kw)
        else:
            return self.do_approve(**kw)

    def action_reject(self):
        kw = self._prepare_action(approval_action='reject')
        approval_template = kw.get('approval_template')
        # approval_template_line = kw.get('approval_template_line')
        # approval_task_line = kw.get('approval_task_line')
        # approval_template_line.check_action_right(approval_task_line, {})
        transaction_object = kw.get('transaction_object')
        approval_template.invoke_method(
            transaction_object, 'validate_reject', kw
        )
        if approval_template.reject_action_type:
            return approval_template.approval_action_custom('reject', **kw)
        else:
            return self.do_reject(**kw)

    def action_cancel(self):
        kw = self._prepare_action(approval_action='cancel')
        approval_template = kw.get('approval_template')
        # kw = approval_template.check_requester_action_right(**kw)
        # approval_template_line = kw.get('approval_template_line')
        # approval_task_line = kw.get('approval_task_line')
        # approval_template_line.check_action_right(approval_task_line, {})
        transaction_object = kw.get('transaction_object')
        approval_template.invoke_method(
            transaction_object, 'validate_cancel', kw
        )
        if approval_template.cancel_action_type:
            return approval_template.approval_action_custom('cancel', **kw)
        else:
            return self.do_cancel(**kw)

    def action_reset_to_draft(self):
        kw = self._prepare_action(approval_action='reset_to_draft')
        approval_template = kw.get('approval_template')
        # kw = approval_template.check_requester_action_right(**kw)
        # approval_template_line = kw.get('approval_template_line')
        # approval_task_line = kw.get('approval_task_line')
        # #kw=approval_template_line.check_requester_action_right(approval_task_line, {})
        transaction_object = kw.get('transaction_object')
        approval_template.invoke_method(
            transaction_object, 'validate_reset_to_draft', kw
        )
        if approval_template.reset_to_draft_action_type:
            return approval_template.approval_action_custom('reset_to_draft', **kw)
        else:
            return self.do_reset_to_draft(**kw)

    def do_reset_to_draft(self, **kw):
        kw = self._prepare_action(approval_action='reset_to_draft', **kw)
        approval_template = kw.get('approval_template')
        kw = approval_template.check_requester_action_right(**kw)
        # approval_instance = self.ensure_one()
        # check_approval = approval_instance.get_next_approval_task_line()
        # approval_template = approval_instance.approval_template_id
        return approval_template.do_reset_to_draft(**kw)

    def action_clear_approval(self):
        self.clear_approval()

    def approve(self, **kwargs):
        return self.do_approve(**kwargs)

    def do_approve(self, **kw):
        kw = self._prepare_action(approval_action='approve', **kw)
        approval_template = kw.get('approval_template')
        return approval_template.do_approve(**kw)

    def before_approve(self, **kwargs):
        if self:
            self.approval_template_id.before_approve(**kwargs)
        else:
            _logger.warning("No Instance for Before Approve")

        return self

    def after_approve(self, **kwargs):
        if self:
            self.approval_template_id.after_approve(**kwargs)
        else:
            _logger.warning("No Instance for After Approve")
        return self

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
        return approval_instance.after_approve(**kw)

    def get_approved_message(self, **kwargs):
        return _("%s has approved this request") % (self.env.user.name)

    def reject(self, reason=None, **kwargs):
        return self.do_reject(reason=reason, **kwargs)

    def do_reject(self, **kw):
        kw = self._prepare_action(approval_action='reject', **kw)
        approval_template = kw.get('approval_template')
        return approval_template.do_reject(**kw)

    def cancel(self, **kw):
        return self.do_cancel(**kw)

    def do_cancel(self, **kw):
        approval_instance = self.ensure_one()
        check_approval = approval_instance.get_next_approval_task_line()
        approval_template = approval_instance.approval_template_id
        kw.setdefault('approval_instance', approval_instance)
        kw.setdefault('approval_task_line', check_approval)
        kw = approval_template.check_requester_action_right(**kw)
        return approval_template.do_cancel(kw)

    def reject_from_popup_reject(self, **kwargs):
        return self.do_reject(**kwargs)

    def before_reject(self, **kwargs):
        if self:
            self.approval_template_id.before_reject(**kwargs)
        else:
            _logger.warning("No Instance for Before Approve")

    def after_reject(self, **kwargs):
        if not self:
            _logger.warning("No Instance for After Reject")
            return self
        if self:
            self.approval_template_id.after_reject(**kwargs)
        else:
            _logger.warning("No Instance for Before Approve")

    @api.model
    def get_rejected_message(self, **kwargs):
        reason = kwargs.get('reason')
        return _('Note Reject => %s') % reason

    def done_approval(self, **kwargs):
        if not self:
            _logger.warning("No Instance for done Approval")
            return self
        approval_instance = self.ensure_one()
        approval_template = approval_instance.approval_template_id
        approval_template.done_approval(**kwargs)

    def clear_approval(self):
        if not self:
            _logger.warning("No Instance for celar Approval")
            return self
        approval_instance = self.ensure_one()
        approval_instance.unregister_approval_task_line()
        approval_task_line = approval_instance.approval_task_line
        if approval_task_line:
            approval_task_line.sudo().unlink()
        approval_template = approval_instance.approval_template_id
        approval_instance.approval_template_id.clear_approval(
            approval_instance=approval_instance,
            approval_template=approval_template,
        )

    def _mail_message_approve(self, message):
        self.env['mail.message'].sudo().create({
            'model': self.transaction_model_name,
            'res_id': self.transaction_id,
            'message_type': 'comment',
            'author_id': self.env.user.partner_id.id,
            'date': datetime.now(),
            'body': message,
        })

    def action_show_sign_pdf(self):
        raise UserError("PDF Sign Not ready.")

    def submit_pdf_document(self, **kwargs):
        raise NotImplemented("submit_pdf_document Not ready to integrate.")

    def sign_pdf_document(self, **kwargs):
        raise NotImplemented("sign_pdf_document Not ready to integrate.")

    def cancel_pdf_document(self, **kwargs):
        raise NotImplemented("cancel_pdf_document Not ready to integrate.")


class ApprovalInstance(models.Model):
    _name = 'approval.instance'
    _inherit = 'approval.instance.mixin'

    approval_document_id = fields.Many2one('approval.document', compute='_compute_approval_document_id')
    approval_template_id = fields.Many2one('approval.template', compute='_compute_approval_template_id')
    approval_task_line_model = fields.Char(related='approval_template_id.approval_task_line_model')
    approval_task_line = fields.One2many('approval.task.line', 'approval_instance_id', string='Approval Task Lines')
    approval_audit_log_ids = fields.Many2many('approval.audit.log', compute="_compute_approval_audit_log_ids")
    user_ids = fields.Many2many('res.users', compute='_compute_approval_users_groups', compute_sudo=True)
    group_ids = fields.Many2many('res.groups', compute='_compute_approval_users_groups', compute_sudo=True)

    @api.depends('model_id', 'model', 'transaction_model_name', 'transaction_id')
    def _compute_approval_document_id(self):
        for rec in self:
            if rec.transaction_id and (rec.transaction_model_name or rec.model):
                transaction_object = rec.get_transaction_object()
                rec.approval_document_id = self.approval_document_id.get_approval_document(transaction_object)
            else:
                rec.approval_document_id = False

    @api.depends('model_id', 'model', 'transaction_model_name')
    def _compute_approval_template_id(self):
        for rec in self:
            rec.approval_template_id = self.approval_template_id.search_template_by_model(
                rec.transaction_model_name or rec.model
            )

    def _compute_approval_audit_log_ids(self):
        for rec in self:
            rec.approval_audit_log_ids = self.approval_audit_log_ids.search(
                [('transaction_id', '=', rec.transaction_id),
                 ('transaction_model_name', '=', rec.transaction_model_name)],
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

    def setup_reject_to_rule_line(self):
        approval_template_line = self.approval_template_line_id
        if approval_template_line:
            _logger.info("Pake approval_template_line %s ", approval_template_line.id)
            approval_task_lines = approval_template_line.get_all_approval_task_line(status=None, approval_instance=self)
            approval_template_line.setup_reject_to_rule_line(approval_task_lines)
        else:
            _logger.info("Not found approval_template_line at instance %s ", self.id)
