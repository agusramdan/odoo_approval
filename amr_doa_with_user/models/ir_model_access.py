# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, tools, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.osv import expression
from odoo.tools import pycompat
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class IrModelAccess(models.Model):
    _inherit = 'ir.model.access'

    # versi 16
    # def _get_allowed_models(self, mode='read'):
    #     return set(super(IrModelAccess,self)._get_allowed_models(mode) | self.env['user.delegation'].get_allowed_models_with_delegation(self.env.uid, mode))

    # versi 13
    def check(self, model, mode='read', raise_exception=True):
        if self.env.su:
            # User root have all accesses
            return True

        assert isinstance(model, str), 'Not a model name: %s' % (model,)
        assert mode in ('read', 'write', 'create', 'unlink'), 'Invalid access mode'

        r = super(IrModelAccess, self).check(model, mode, raise_exception=False)
        # TransientModel records have no access rights, only an implicit access rule
        if not r:
            if model not in self.env:
                _logger.error('Missing model %s', model)
            elif self.env[model].is_transient():
                return True
            self.flush(self._fields)
            r = self.env['user.delegation'].check_model_access_with_delegation(self.env.uid, model, mode)

        if not r and raise_exception:
            groups = '\n'.join('\t- %s' % g for g in self.group_names_with_access(model, mode))
            msg_heads = {
                # Messages are declared in extenso so they are properly exported in translation terms
                'read': _("Sorry, you are not allowed to access documents of type '%(document_kind)s' (%(document_model)s)."),
                'write':  _("Sorry, you are not allowed to modify documents of type '%(document_kind)s' (%(document_model)s)."),
                'create': _("Sorry, you are not allowed to create documents of type '%(document_kind)s' (%(document_model)s)."),
                'unlink': _("Sorry, you are not allowed to delete documents of type '%(document_kind)s' (%(document_model)s)."),
            }
            msg_params = {
                'document_kind': self.env['ir.model']._get(model).name or model,
                'document_model': model,
            }
            if groups:
                msg_tail = _("This operation is allowed for the groups:\n%(groups_list)s")
                msg_params['groups_list'] = groups
            else:
                msg_tail = _("No group currently allows this operation.")
            msg_tail += u' - ({} {}, {} {})'.format(_('Operation:'), mode, _('User:'), self._uid)
            _logger.info('Access Denied by ACLs for operation: %s, uid: %s, model: %s', mode, self._uid, model)
            msg = '%s %s' % (msg_heads[mode], msg_tail)
            raise AccessError(msg % msg_params)

        return bool(r)
