# -*- coding: utf-8 -*-

import base64
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

EXCLUDE_MODELS = {
    # Technical
    'ir.model',
    'ir.model.fields',
    'ir.cron',
    'ir.ui.view',
    'ir.actions.act_window',

    # Security
    'res.users',
    'res.groups',
    'res.company',
    'res.config.settings',

    # Messaging
    'mail.message',
    'mail.followers',
    'mail.activity',

    #
    'internal.data.event',
    'internal.data.event.config',
    'external.data.event',
}

EXCLUDE_PREFIXES = (
    'ir.',
    'bus.',
    'base.',
    'mail.',
    'web.',
    'internal.data.',
    'external.data.',
    'application.',
    'approval.',
    'notification.'
    'user.delegation.'
    'whatsapp.'
)


def have_method(obj, method):
    return method and isinstance(method, str) and hasattr(obj, method) and callable(getattr(obj, method))


def is_excluded(model_name):
    return model_name in EXCLUDE_MODELS or model_name.startswith(EXCLUDE_PREFIXES)


class ApprovalTaskLineBaseMixin(models.AbstractModel):
    _inherit = 'base'

    def get_approval_template_line(self):
        return self.env['approval.template.line'].search_template_line_by_model(self._name)

    def _is_excluded(self):
        return is_excluded(self._name)

    def state_leave_waiting_approvals(self, approval_template_line, state_approval, create_date=None):
        rec = self
        al = None
        if approval_template_line.state_approved == state_approval:
            _logger.info("To Approve %s , %s .", rec.display_name, state_approval)
            al = self.env['approval.audit.log'].create_approval_audit_log_approved(
                approval_task_line=rec,
                create_date=create_date or fields.Datetime.now(),
            )
        elif approval_template_line.state_rejected == state_approval:
            _logger.info("To Reject %s , %s .", rec.display_name, state_approval)
            al = self.env['approval.audit.log'].create_approval_audit_log_rejected(
                approval_task_line=rec,
                create_date=create_date or fields.Datetime.now(),
            )
        elif approval_template_line.state_canceled == state_approval:
            al = self.env['approval.audit.log'].create_approval_audit_log_canceled(
                approval_task_line=rec,
                create_date=create_date or fields.Datetime.now(),
            )
            _logger.info("To Cancel %s , %s .", rec.display_name, state_approval)
        else:
            _logger.warning("%s , %s .", rec.display_name, state_approval)
        return al

    def write(self, vals):
        if self.is_transient() or self._is_excluded() or self.env.context.get(
                '__skip_approval_task_line_status') or self.is_transient():
            return super().write(vals)
        approval_template_line = self.get_approval_template_line()
        if not approval_template_line:
            return super().write(vals)
        approval_template = approval_template_line.approval_template_id
        if not approval_template:
            approval_template = self.env['approval.template'].get_approval_template(
                approval_task_line=self, approval_template_line=approval_template_line
            )
        old = None
        state_field = None
        trx_change = {}

        if approval_template_line and approval_template_line.state_field:
            state_field = approval_template_line.state_field
            if state_field in vals:
                old = {r.id: getattr(r, state_field, None) for r in self}
        res = super().write(vals)
        if old:
            state_waiting_approvals = approval_template_line.get_state_waiting_approvals()
            for rec in self:
                state_approval = getattr(rec, state_field)
                if old[rec.id] in state_waiting_approvals and state_approval not in state_waiting_approvals:
                    transaction_object = approval_template_line.get_transaction_object(
                        approval_template=approval_template,
                        approval_template_line=approval_template_line,
                        approval_task_line=rec,
                    )
                    trx_change[transaction_object.id] = transaction_object
                    rec.state_leave_waiting_approvals(approval_template_line, state_approval)

        if (
                trx_change and
                approval_template_line and
                approval_template_line.auto_register_approval_task and
                not self.env.context.get('__skip_auto_register_approval_task_line_status')
        ):
            for trx_id, transaction_object in trx_change.items():
                approval_task_line = None
                approval_instance = None
                if transaction_object:
                    approval_instance = self.env['approval.instance'].create_or_get(
                        transaction=transaction_object,
                        approval_template=approval_template,
                        approval_template_line=approval_template_line,
                        raise_exception_without_template=False,
                    )
                    if approval_instance:
                        approval_task_line = approval_instance.get_next_approval_task_line()
                if (
                        approval_task_line and
                        transaction_object and
                        approval_instance and
                        approval_instance.is_status_waiting_approval()
                ):
                    if have_method(transaction_object, 'register_to_approval_task'):
                        transaction_object.register_to_approval_task(
                            approval_task_line=approval_task_line,
                            approval_template=approval_template,
                            approval_template_line=approval_template_line,
                        )
                    else:
                        approval_instance.register_approval_task_line(
                            transaction_object=transaction_object,
                            approval_task_line=approval_task_line,
                            approval_template=approval_template,
                            approval_template_line=approval_template_line,
                        )

        return res
