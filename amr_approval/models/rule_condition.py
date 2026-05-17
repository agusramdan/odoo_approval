# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval, test_python_expr

DEFAULT_CODE = """
# Available variables:
#----------------------
result = transaction_value>10
"""


class RuleCondition(models.AbstractModel):
    _name = "rule.condition.mixin"
    _description = "Capture rule condition"

    condition_select = fields.Selection(
        [("none", "Always True"),
         ('tiring', 'Tiring'),
         ('limit', 'Limit'),
         ("range", "Range"),
         ("python", "Python Expression"),
         ],
        string="Condition Based on",
        default="none",
        required=True,
    )
    condition_range = fields.Char(
        string="Range Based on",
        default="transaction_value",
        help="This will be used to compute the % fields values; in general it ",
    )
    condition_python = fields.Text(
        string="Python Condition",
        required=True,
        default=DEFAULT_CODE,
        help="Applied this rule for calculation if condition is true. You can "
        "specify condition like basic > 1000.",
    )
    condition_range_min = fields.Float(
        string="Minimum Range", help="The minimum amount, applied for this rule."
    )
    condition_range_max = fields.Float(
        string="Maximum Range", help="The maximum amount, applied for this rule."
    )

    def is_satisfy_condition(self, localdict):

        self.ensure_one()

        if self.condition_select == "none":
            return True
        elif self.condition_select == "tiring":
            try:
                result = safe_eval(self.condition_range, localdict)
                return (
                    self.condition_range_min <= result
                    or False
                )
            except Exception:
                raise UserError(
                    _("Wrong tiring condition defined for rule %s.")
                    % self.display_name
                )
        elif self.condition_select == "limit":
            try:
                result = safe_eval(self.condition_range, localdict)
                return (
                    result <= self.condition_range_max
                    or False
                )
            except Exception:
                raise UserError(
                    _("Wrong limit condition defined for rule %s .")
                    % self.display_name
                )
        elif self.condition_select == "range":
            try:
                result = safe_eval(self.condition_range, localdict)
                return (
                    self.condition_range_min <= result <= self.condition_range_max
                    or False
                )
            except Exception:
                raise UserError(
                    _("Wrong range condition defined for rule %s .")
                    % self.display_name
                )
        elif self.condition_select == 'python':  # python code
            try:
                safe_eval(self.condition_python, localdict, mode="exec", nocopy=True)
                return "result" in localdict and localdict["result"] or False
            except Exception:
                raise UserError(
                    _("Wrong python condition defined for rule %s.")
                    % self.display_name
                )
        else:
            return False

    @api.constrains('condition_python')
    def _check_python_code(self):
        for action in self.sudo().filtered(lambda r: r.condition_select == 'python' and r.condition_python):
            msg = test_python_expr(expr=action.condition_python.strip(), mode="exec")
            if msg:
                raise ValidationError(msg)

    def action_open_condition_editor(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Condition Editor',
            'res_model': 'rule.condition.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'active_model': self._name,
            }
        }
