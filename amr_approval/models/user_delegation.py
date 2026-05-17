# -*- coding: utf-8 -*-

import logging

from odoo import _ ,models, fields, api, tools
from datetime import date
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class UserDelegation(models.Model):
    _name = 'user.delegation'
    _description = 'User Delegation'
    _order = 'start_date desc'
    _inherit = ['mail.thread']

    active = fields.Boolean(default=True)
    name = fields.Char(
        string='Delegation Number',
        default='Draft',
        required=True,
        tracking=True,
        copy=False
    )
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        string='Company', tracking=True,
        help="Company for which the delegation is valid."
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('prepared', 'Prepared'),
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ], string='State', default='draft', tracking=True)
    notification_option = fields.Selection(
        [('send_to_delegatee_only', 'Notif to Delegatee Only'),
         ('send_to_both', 'Notif to delegator & delegatee')],
        default='send_to_both'
    )
    delegator_id = fields.Many2one(
        'res.users', string='Delegator', required=True, tracking=True, default=lambda self: self.env.user
    )
    delegator_group_ids = fields.Many2many(
        'res.groups',
        string='Delegator Groups',
        compute='_compute_delegator_group_ids',
        store=False,  # jika ingin nilainya disimpan di DB
        readonly=True,  # agar tidak bisa diubah manual
        help="Groups of the delegator user. Used for filtering delegations."
    )
    delegatee_id = fields.Many2one(
        'res.users',
        string='Delegatee (Acting On Behalf)',
        tracking=True, store=True, readonly=False,
        help="User who will act on behalf of the delegator."
    )
    start_date = fields.Date(string='Start Date', required=True, tracking=True, )
    end_date = fields.Date(string='End Date', required=True, tracking=True, )
    note = fields.Text(string="Notes")
    is_prepared_condition = fields.Boolean(compute='compute_is_condition')
    is_edit_able_delegator_id = fields.Boolean(compute='compute_is_condition')
    is_able_button_revoke = fields.Boolean(compute='compute_is_condition')
    filter_user_delegation = fields.Boolean(store=False, search="search_filter_user_delegation")

    @api.depends('delegator_id')
    def _compute_delegator_group_ids(self):
        for rec in self:
            if rec.delegator_id:
                rec.delegator_group_ids = rec.delegator_id.groups_id
            else:
                rec.delegator_group_ids = [(5, 0, 0)]

    def name_get(self):
        return [
            (record.id, f"[{record.name}] {record.delegator_id.name} to {record.delegatee_id.name}")
            for record in self
        ]

    def ensure_set_number(self):
        name = self.name or _('Draft')
        if name in [_('Draft'), _('New')] and self.state != 'draft':
            vals = self.setup_number({'name': name})
            self.write(vals)

    def _set_prepared_state(self):
        self.ensure_one()
        self.ensure_set_number()
        if self.state in ['cancelled', 'expired']:
            return
        else:
            self.ensure_state()

    def ensure_state(self):
        today = date.today()
        if self.start_date <= today <= self.end_date:
            self.state = 'active'
        elif self.start_date > today:
            self.state = 'prepared'
        elif self.end_date < today:
            self.state = 'expired'

    def action_button_submit(self):
        self._set_prepared_state()

    def action_button_cancel(self):
        self.state = 'cancelled'

    def action_button_revoke(self):
        self.state = 'expired'

    @api.model
    def get_prepared_state(self):
        return ['prepared']

    @api.depends('state')
    def compute_is_condition(self):
        for rec in self:
            rec.is_edit_able_delegator_id = rec.state == 'draft' and self.user_has_groups('base.group_erp_manager')
            rec.is_able_button_revoke = rec.state == 'active' and (
                    rec.delegator_id.id == self.env.user.id or self.user_has_groups('base.group_erp_manager'))
            rec.is_prepared_condition = rec.state in self.get_prepared_state() and (
                    rec.delegator_id.id == self.env.user.id or self.user_has_groups('base.group_erp_manager'))

    def search_filter_user_delegation(self, operator, operand):
        if self.user_has_groups('base.group_erp_manager'):
            return []
        else:
            return ['|', ('delegator_id', '=', self.env.user.id), ('delegatee_id', '=', self.env.user.id)]

    def cron_update_delegation_state(self):
        """
        Cron job to update the state of delegations based on current date.
        """
        delegations = self.search([('state', 'in', self.get_prepared_state())])
        for delegation in delegations:
            delegation.ensure_state()
            delegation.ensure_set_number()

    @api.constrains('delegator_id', 'delegatee_id')
    def _check_different_users(self):
        for rec in self:
            if rec.delegator_id == rec.delegatee_id:
                raise ValidationError("Delegator and Delegatee cannot be the same user.")

    def setup_number(self, vals):
        if vals.get('name', _('Draft')) in [_('Draft'), _('New'), '/', False]:
            find_dcr = True
            while find_dcr:
                name = self.env['ir.sequence'].next_by_code('user.delegation')
                if name:
                    vals['name'] = self.env['ir.sequence'].next_by_code('user.delegation')
                    find_dcr = self.search([('name', '=', vals['name'])], limit=1)
                else:
                    find_dcr = False
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        new_vals_list = []
        for vals in vals_list:
            new_vals_list.append(self.setup_number(vals))
        records = super().create(new_vals_list)
        return records

    # def unlink(self):
    #     active_records = self.filtered(lambda r: r.state == 'active')
    #     proxies = active_records.mapped('delegatee_id')
    #     res = super().unlink()
    #     for proxy in proxies:
    #         self.get_delegations_user_group_for_proxy.clear_cache(self, proxy.id)
    #     return res

    @api.constrains('delegator_id', 'delegatee_id', 'start_date', 'end_date', 'state')
    def _check_duplicate_active_delegation(self):
        for rec in self:
            if rec.state == 'cancelled':
                continue
            overlaps = self.search([
                ('id', '!=', rec.id),
                ('state', '=', 'active'),
                ('delegator_id', '=', rec.delegator_id.id),
                ('delegatee_id', '=', rec.delegatee_id.id),
                ('start_date', '<=', rec.end_date),
                ('end_date', '>=', rec.start_date),
            ])
            if overlaps:
                raise ValidationError("Duplicate active delegation with overlapping period found.")

    # @tools.ormcache('delegatee_id', 'group_id')
    # def has_delegate_group(self, delegatee_id, group_id):
    #     """
    #     Checks this user as proxy user have DoA form delegator user given group delegator user to proxy user.
    #     """
    #     self._cr.execute("""
    #             SELECT 1
    #             FROM user_delegation ud
    #             JOIN res_groups_users_rel gu ON gu.uid = ud.delegator_id
    #             WHERE
    #                 ud.delegatee_id = %s
    #                 AND gu.gid = %s
    #                 AND ud.state = 'active'
    #                 AND ud.start_date <= CURRENT_DATE
    #                 AND ud.end_date >= CURRENT_DATE
    #             LIMIT 1
    #         """, (delegatee_id, group_id))
    #     return bool(self._cr.fetchone())

    # def _clear_delegatee_cache_if_needed(self, old_vals=None):
    #     """
    #     Bersihkan cache hanya jika:
    #     - state berubah menjadi atau dari 'active'
    #     - atau field penting pada delegasi aktif berubah
    #     """
    #     tracked_fields = {'start_date', 'end_date', 'delegator_id', 'delegatee_id', 'state'}
    #
    #     for rec in self:
    #         need_clear = False
    #
    #         # Jika tidak disediakan, bersihkan saja tanpa pengecekan
    #         if old_vals is None:
    #             need_clear = True
    #         else:
    #             # Cek perubahan state
    #             old_state = old_vals.get(rec.id, {}).get('state')
    #             new_state = rec.state
    #             if old_state != new_state and ('active' in (old_state, new_state)):
    #                 need_clear = True
    #
    #             # Jika state tetap 'active', cek field lain berubah
    #             if old_state == 'active' and new_state == 'active':
    #                 for field in tracked_fields:
    #                     if field in old_vals.get(rec.id, {}):
    #                         need_clear = True
    #                         break
    #
    #         if need_clear and rec.delegatee_id:
    #             _logger.debug("Clearing cache for delegatee_id=%s due to state/field change.", rec.delegatee_id.id)
    #             self.get_delegations_user_group_for_proxy.clear_cache(self, rec.delegatee_id.id)
    #
    #             if rec.delegator_id:
    #                 for group in rec.delegator_id.groups_id:
    #                     self.has_delegate_group.clear_cache(self, rec.delegatee_id.id, group.id)
    #
    # def get_all_delegations(self, delegatee_id=None, delegator_id=None, group_id=None, company_id=None, limit=None):
    #     """
    #     Ambil delegasi aktif untuk proxy tertentu.
    #     Jika group_id diberikan, hanya delegator yang termasuk dalam grup tersebut.
    #     """
    #     today = date.today()
    #     domain = [
    #         ('start_date', '<=', today),
    #         ('end_date', '>=', today),
    #         ('state', '=', 'active'),
    #         ('active', '=', True),
    #     ]
    #     if company_id:
    #         domain.extend([
    #             ('delegator_id.company_ids', '=', int(company_id)),
    #             ('delegatee_id.company_ids', '=', int(company_id))
    #         ])
    #
    #     if delegatee_id:
    #         if isinstance(delegatee_id, list):
    #             domain.append(('delegatee_id', 'in', delegatee_id))
    #         else:
    #             domain.append(('delegatee_id', '=', delegatee_id))
    #
    #     if delegator_id:
    #         if isinstance(delegator_id, list):
    #             domain.append(('delegator_id', 'in', delegator_id))
    #         else:
    #             domain.append(('delegator_id', '=', delegator_id))
    #
    #     if group_id:
    #         if isinstance(group_id, list):
    #             domain.append(('group_id', 'in', group_id))
    #         else:
    #             domain.append(('group_id', '=', group_id))
    #
    #     return self.search(domain, limit=limit, order='start_date desc,end_date')
    #
    # def get_notification_user_ids(self, delegator_ids, company_id=None):
    #     delegations = self.get_all_delegations(delegator_id=delegator_ids, company_id=company_id)
    #     result = []
    #     exclude_user_delegation = []
    #     for delegation in delegations:
    #         result.append(delegation.delegatee_id.id)
    #         if delegation.notification_option == 'send_to_delegatee_only':
    #             exclude_user_delegation.append(delegation.delegator_id.id)
    #         else:
    #             result.append(delegation.delegator_id.id)
    #     result.extend(set(delegator_ids) - set(exclude_user_delegation))
    #     return list(set(result))
    #
    # def get_all_delegatee(self, delegator_ids, company_id=None):
    #     """
    #     get delegatee_ids for this delegator_ids
    #     """
    #     if not delegator_ids:
    #         return []
    #     delegations = self.get_all_delegations(delegator_id=delegator_ids, company_id=company_id)
    #     return list(
    #         set(d.delegatee_id.id for d in delegations) - set(delegator_ids)
    #     )

    # def get_all_delegator(self, delegatee_ids, company_id=None):
    #     """
    #     get delegator for this delegatee_ids
    #     """
    #     if not delegatee_ids:
    #         return []
    #     delegations = self.get_all_delegations(delegatee_id=delegatee_ids, company_id=company_id)
    #     return list(
    #         set(d.delegator_id.id for d in delegations) - set(delegatee_ids)
    #     )

    @api.model
    def read_user(self, user):
        # expectasi bahwa res.users hanya akan lookup saja tanpa melakukanan create bila tidak ditemukan
        # pencarian bisa menggunakan email atau id di aplikasi penerima

        if not user:
            return None
        return {
            'id': user.id,
            'name': user.name,
            'login': user.login,
            'email': user.email,
        }

    def read(self, fields=None, load='_classic_read'):
        if self.env.context.get('__from_sync_data_api') or self.env.context.get('__read_data_for_sync_external_application'):
            if fields:
                if 'delegator_group_ids' in fields:
                    fields.remove('delegator_group_ids')

        result = super(UserDelegation, self).read(fields=fields, load=load)
        if self.env.context.get('__from_sync_data_api') or self.env.context.get('__read_data_for_sync_external_application'):
            delegator = {}
            for rec in self:
                delegator[rec.id] = {
                    'write_date': rec.write_date,
                }
                if rec.delegator_id and (not fields or (fields and 'delegator_id' in fields)):
                    delegator[rec.id]['delegator_id'] = self.read_user(rec.delegator_id)

                if rec.delegatee_id and (not fields or (fields and 'delegatee_id' in fields)):
                    delegator[rec.id]['delegatee_id'] = self.read_user(rec.delegatee_id)

            if len(result) > 0:
                for data in result:
                    if data['id'] not in delegator:
                        continue
                    data.update(
                        delegator[data['id']]
                    )

        return result
