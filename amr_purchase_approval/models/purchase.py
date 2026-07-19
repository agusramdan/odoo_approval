# -*- encoding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _name = 'purchase.order'
    _inherit = [_name, 'approval.instance.able.mixin']

    state = fields.Selection(selection_add=[
        ('draft',),
        ('waiting_approval', 'Waiting Approval'),
        ('approved', 'Approved'),
        ('reject', 'Reject'),
        ('cancel', 'Cancel'),
    ])
    # def write(self, vals):
    #     result = super(PurchaseOrder, self).write(vals)
    #     if vals.get('requisition_id'):
    #         self.message_post_with_view('mail.message_origin_link',
    #                 values={'self': self, 'origin': self.requisition_id, 'edit': True},
    #                 subtype_id=self.env['ir.model.data'].xmlid_to_res_id('mail.mt_note'))
    #     return result


# class PurchaseOrderLine(models.Model):
#     _inherit = 'purchase.order.line'
#
#     @api.onchange('product_qty', 'product_uom')
#     def _onchange_quantity(self):
#         res = super(PurchaseOrderLine, self)._onchange_quantity()
#         if self.order_id.requisition_id:
#             for line in self.order_id.requisition_id.line_ids.filtered(lambda l: l.product_id == self.product_id):
#                 if line.product_uom_id != self.product_uom:
#                     self.price_unit = line.product_uom_id._compute_price(
#                         line.price_unit, self.product_uom)
#                 else:
#                     self.price_unit = line.price_unit
#                 break
#         return res
