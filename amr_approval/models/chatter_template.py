# -*- coding: utf-8 -*-

import json
import logging
import traceback

from odoo import api, fields, models
from ..tools.utils import safe_call_method, have_method, remove_odoo_objects, normalize_binary
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval, test_python_expr
from odoo.tools.misc import clean_context
from odoo.tools import plaintext2html

_logger = logging.getLogger(__name__)

DEFAULT_PYTHON_CODE = """# Available variables:
#  - ctx: Contex
#  - object: Object
#  - record: Record
#  - kwargs: kwargs 
#  - env: Odoo Environment on which the action is triggered
#  - body
# To return an body
\n\n\n\n
"""


class ChatterTemplate(models.Model):
    _name = "chatter.template"
    _description = "Chatter Template"

    active = fields.Boolean(default=True)
    name = fields.Char("Chatter")
    model_id = fields.Many2one('ir.model')
    model = fields.Char(related='model_id.model', store=True)
    chatter_type = fields.Selection(
        [
            ('approval', 'Request Approval'),
            ('cancel', 'Cancel'),
            ('reset', 'Reset To Draft'),
            ('reject', 'Rejection'),
            ('approve', 'Approve'),
        ],
    )
    body = fields.Text()
    code = fields.Text(
        string='Python Code',
        default=DEFAULT_PYTHON_CODE,
        help="Write Python code that the action will execute. Some variables are "
             "available for use; help about python expression is given in the help tab."
    )

    def get_chatter_message(self, res_id=False, **kwargs):
        _logger.info('get_chatter_message')
        new_res_id = self.ensure_res_id(**kwargs) or res_id
        body = ""
        if new_res_id != new_res_id:
            _logger.info("change res_id from %s to %s", res_id, new_res_id)
            res_id = new_res_id

        if res_id and self.env[self.model].sudo().browse(res_id):
            _logger.warning("data %s and %s", self.model, res_id)

            template = self.ensure_one()
            ctx = clean_context(self.env.context)
            # v13
            renderer = self.env['mail.template'].sudo().with_context(ctx)
            # v16
            # renderer = self.env['mail.render.mixin'].sudo().with_context(ctx)
            try:
                # v16
                # if field in ['body_html', 'body_chat']:
                #     engine = "qweb"
                # else:
                #     engine = 'inline_template'
                # request[field] = renderer._render_template(
                #     getattr(template, field), template.model, [res_id], engine=engine,
                # )[res_id]
                # v13
                body = renderer._render_template(template.body, template.model, res_id)
            except Exception:
                _logger.exception("field body_chatter", )

        eval_context = self._get_eval_context()
        record = self.env[self.model].sudo().browse(res_id)
        eval_context['res_id'] = res_id
        eval_context['body'] = body
        eval_context['object'] = eval_context['record'] = record
        eval_context['kwargs'] = kwargs
        eval_context = self._run_action_code_multi(eval_context)
        return eval_context['body']

    @api.model
    def _get_eval_context(self):
        """ evaluation context to pass to safe_eval """
        return {
            'approval_notification_template_chatter': self,
            'env': self.env,
            'uid': self._uid,
            'user': self.env.user,
        }

    @api.constrains('code')
    def _check_python_code(self):
        for action in self.sudo().filtered('code'):
            msg = test_python_expr(expr=action.code.strip(), mode="exec")
            if msg:
                raise ValidationError(msg)

    def _run_action_code_multi(self, eval_context):
        safe_eval(self.code.strip(), eval_context, mode="exec", nocopy=True)  # nocopy allows to return 'action'
        return eval_context

    @api.model
    def send_message_post(self, transaction_object, message, **kwargs):
        if not transaction_object:
            return
        if have_method(transaction_object, "message_post"):
            return transaction_object.sudo().message_post(body=message, author_id=self.env.user.partner_id.id)
        else:
            _logger.info("Tidak ada message_post %s ", transaction_object)
        return

    def run_action_chatter(self, eval_context):
        self.ensure_one()
        eval_context['res_id'] = eval_context.get('action_id') or eval_context.get('res_id')
        message = self.get_chatter_message(**eval_context)
        transaction_object = eval_context.get('transaction_object') or self.env.context.get('transaction_object') or self.env[self.model].browse(eval_context.get('res_id'))
        self.send_message_post(transaction_object, message, **eval_context)
        return False
