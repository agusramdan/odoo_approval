# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools
from odoo.fields import Many2one, One2many, Many2many
from datetime import date
from odoo.exceptions import ValidationError

import logging

_logger = logging.getLogger(__name__)


class UserDelegation(models.Model):
    _inherit = 'user.delegation'

    def unlink(self):
        active_records = self.filtered(lambda r: r.state == 'active')
        proxies = active_records.mapped('delegatee_id')
        res = super().unlink()
        if proxies:
            self.get_delegations_user_group_for_delegatee.clear_cache(self)
            self.check_model_access_with_delegation.clear_cache(self)
            self.get_allowed_models_with_delegation.clear_cache(self)
            self.env['ir.model.access'].call_cache_clearing_methods()
        return res

    def write(self, write_vals):
        r = super(UserDelegation, self).write(write_vals)
        if not write_vals.get('state') == 'active':
            self.get_delegations_user_group_for_delegatee.clear_cache(self)
            self.check_model_access_with_delegation.clear_cache(self)
            self.env['ir.model.access'].call_cache_clearing_methods()
        return r

    @tools.ormcache('delegatee_id', 'group_id')
    def has_delegate_group(self, delegatee_id, group_id):
        """
        Checks this user as proxy user have DoA form delegator user given group delegator user to proxy user.
        """
        self._cr.execute("""
                SELECT 1
                FROM user_delegation ud
                JOIN res_groups_users_rel gu ON gu.uid = ud.delegator_id
                WHERE
                    ud.delegatee_id = %s
                    AND gu.gid = %s
                    AND ud.state = 'active'
                    AND ud.start_date <= CURRENT_DATE
                    AND ud.end_date >= CURRENT_DATE
                LIMIT 1
            """, (delegatee_id, group_id))
        return bool(self._cr.fetchone())

    def _clear_delegatee_cache_if_needed(self, old_vals=None):
        """
        Bersihkan cache hanya jika:
        - state berubah menjadi atau dari 'active'
        - atau field penting pada delegasi aktif berubah
        """
        tracked_fields = {'start_date', 'end_date', 'delegator_id', 'delegatee_id', 'state'}

        for rec in self:
            need_clear = False

            # Jika tidak disediakan, bersihkan saja tanpa pengecekan
            if old_vals is None:
                need_clear = True
            else:
                # Cek perubahan state
                old_state = old_vals.get(rec.id, {}).get('state')
                new_state = rec.state
                if old_state != new_state and ('active' in (old_state, new_state)):
                    need_clear = True

                # Jika state tetap 'active', cek field lain berubah
                if old_state == 'active' and new_state == 'active':
                    for field in tracked_fields:
                        if field in old_vals.get(rec.id, {}):
                            need_clear = True
                            break

            if need_clear and rec.delegatee_id:
                _logger.debug("Clearing cache for delegatee_id=%s due to state/field change.", rec.delegatee_id.id)
                self.get_delegations_user_group_for_delegatee.clear_cache(self, rec.delegatee_id.id)

                if rec.delegator_id:
                    for group in rec.delegator_id.groups_id:
                        self.has_delegate_group.clear_cache(self, rec.delegatee_id.id, group.id)

    def get_all_delegations(self, delegatee_id=None, delegator_id=None, group_id=None, company_id=None, limit=None):
        """
        Ambil delegasi aktif untuk proxy tertentu.
        Jika group_id diberikan, hanya delegator yang termasuk dalam grup tersebut.
        """
        today = date.today()
        domain = [
            ('start_date', '<=', today),
            ('end_date', '>=', today),
            ('state', '=', 'active'),
            ('active', '=', True),
        ]
        if company_id:
            domain.extend([
                ('delegator_id.company_ids', '=', int(company_id)),
                ('delegatee_id.company_ids', '=', int(company_id))
            ])

        if delegatee_id:
            if isinstance(delegatee_id, list):
                domain.append(('delegatee_id', 'in', delegatee_id))
            else:
                domain.append(('delegatee_id', '=', delegatee_id))

        if delegator_id:
            if isinstance(delegator_id, list):
                domain.append(('delegator_id', 'in', delegator_id))
            else:
                domain.append(('delegator_id', '=', delegator_id))

        if group_id:
            if isinstance(group_id, list):
                domain.append(('delegator_id.group_id', 'in', group_id))
            else:
                domain.append(('delegator_id.group_id', '=', group_id))

        return self.sudo().search(domain, limit=limit, order='start_date desc,end_date')

    def get_notification_user_ids(self, delegator_ids, company_id=None):
        delegations = self.get_all_delegations(delegator_id=delegator_ids, company_id=company_id)
        result = []
        exclude_user_delegation = []
        for delegation in delegations:
            result.append(delegation.delegatee_id.id)
            if delegation.notification_option == 'send_to_delegatee_only':
                exclude_user_delegation.append(delegation.delegator_id.id)
            else:
                result.append(delegation.delegator_id.id)
        result.extend(set(delegator_ids) - set(exclude_user_delegation))
        return list(set(result))

    def get_all_delegatee(self, delegator_ids, company_id=None):
        """
        get delegatee_ids for this delegator_ids
        """
        if not delegator_ids:
            return []
        delegations = self.get_all_delegations(delegator_id=delegator_ids, company_id=company_id)
        return list(
            set(d.delegatee_id.id for d in delegations) - set(delegator_ids)
        )

    def get_all_delegator(self, delegatee_ids, company_id=None):
        """
        get delegator for this delegatee_ids
        """
        if not delegatee_ids:
            return []
        delegations = self.get_all_delegations(delegatee_id=delegatee_ids, company_id=company_id)
        return list(
            set(d.delegator_id.id for d in delegations) - set(delegatee_ids)
        )

    @tools.ormcache('delegatee_id')
    def get_delegations_user_group_for_delegatee(self, delegatee_id):

        _logger.debug("Getting delegation info from DB for delegatee_id=%s (SQL)", delegatee_id)
        self._cr.execute("""
                    SELECT DISTINCT ud.id, ud.delegator_id, gu.gid
                    FROM user_delegation ud
                    JOIN res_groups_users_rel gu ON gu.uid = ud.delegator_id
                    WHERE
                        ud.delegatee_id = %s
                        AND ud.state = 'active'
                        AND ud.start_date <= CURRENT_DATE
                        AND ud.end_date >= CURRENT_DATE
                """, (delegatee_id,))
        rows = self._cr.fetchall()

        # Pisahkan jadi dua set
        user_ids = set()
        group_ids = set()
        user_delegate_ids = set()
        for udid, uid, gid in rows:
            user_ids.add(uid)
            group_ids.add(gid)
            user_delegate_ids.add(udid)
        group_ids = group_ids - set(self.env['res.users'].doa_exclude_groups().ids)
        return {
            'user_ids': list(user_ids),
            'group_ids': list(group_ids),
            'user_delegate_ids': list(user_delegate_ids),
        }

    @tools.ormcache('uid', 'model', 'mode')
    def check_model_access_with_delegation(self, uid, model, mode='read'):
        data = self.env['user.delegation'].get_delegations_user_group_for_delegatee(uid)
        group_ids = data['group_ids']
        if not group_ids:
            return False

        self._cr.execute("""SELECT MAX(CASE WHEN perm_{mode} THEN 1 ELSE 0 END)
                                          FROM ir_model_access a
                                          JOIN ir_model m ON (m.id = a.model_id)
                                         WHERE m.model = %s
                                           AND a.group_id = ANY(%s)
                                           AND a.active IS TRUE""".format(mode=mode),
                         (model, group_ids,))
        r = self._cr.fetchone()[0]
        return bool(r)

    # Version 16
    @tools.ormcache('uid', 'mode')
    def get_allowed_models_with_delegation(self, uid, mode='read'):
        assert mode in ('read', 'write', 'create', 'unlink'), 'Invalid access mode'
        data = self.env['user.delegation'].get_delegations_user_group_for_delegatee(uid)
        group_ids = data['group_ids']
        self.flush_model()
        self.env.cr.execute(f"""
                SELECT m.model
                  FROM ir_model_access a
                  JOIN ir_model m ON (m.id = a.model_id)
                WHERE a.perm_{mode}
                   AND a.active
                   AND (
                        a.group_id IS NULL OR
                        a.group_id = ANY(%s)
                    )
                GROUP BY m.model
            """, (group_ids,))
        r = frozenset(v[0] for v in self.env.cr.fetchall())
        _logger.info("r", r)
        return r
