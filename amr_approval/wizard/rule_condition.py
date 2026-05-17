from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval

DEFAULT_CODE = """
# Available variables:
# transaction_value
# employee
# transaction

result = transaction_value > 1000000
"""


class RuleConditionWizard(models.TransientModel):
    _name = 'rule.condition.wizard'
    _description = 'Rule Condition Wizard'

    condition_select = fields.Selection([
        ('none', 'Always True'),
        ('range', 'Range'),
        ('python', 'Python Expression'),
    ], required=True, default='none')

    # RANGE
    condition_range = fields.Char(
        string='Range Based On',
        default='transaction_value'
    )

    condition_range_min = fields.Float(
        string='Minimum Range'
    )

    condition_range_max = fields.Float(
        string='Maximum Range'
    )

    # PYTHON
    condition_python = fields.Text(
        string='Python Condition',
        default=DEFAULT_CODE
    )

    test_value = fields.Float(
        default=0
    )

    test_result = fields.Boolean(
        readonly=True
    )

    @api.model
    def default_get(self, fields_list):

        res = super().default_get(fields_list)

        active_id = self.env.context.get('active_id')
        active_model = self.env.context.get('active_model')

        if active_id and active_model:
            record = self.env[active_model].browse(active_id)

            res.update({
                'condition_select': record.condition_select,
                'condition_range': record.condition_range,
                'condition_range_min': record.condition_range_min,
                'condition_range_max': record.condition_range_max,
                'condition_python': record.condition_python,
            })

        return res

    def action_apply(self):

        self.ensure_one()

        active_id = self.env.context.get('active_id')
        active_model = self.env.context.get('active_model')

        if not active_id:
            return

        record = self.env[active_model].browse(active_id)

        values = {
            'condition_select': self.condition_select,
            'condition_range': self.condition_range,
            'condition_range_min': self.condition_range_min,
            'condition_range_max': self.condition_range_max,
            'condition_python': self.condition_python,
        }

        record.write(values)

        return {'type': 'ir.actions.act_window_close'}

    def action_test(self):

        self.ensure_one()

        localdict = {
            'transaction_value': self.test_value,
        }

        result = False

        if self.condition_select == 'none':

            result = True

        elif self.condition_select == 'range':

            value = safe_eval(
                self.condition_range,
                localdict
            )

            result = (
                    self.condition_range_min
                    <= value
                    <= self.condition_range_max
            )

        else:

            safe_eval(
                self.condition_python,
                localdict,
                mode='exec',
                nocopy=True
            )

            result = localdict.get('result', False)

        self.test_result = result
        return {}
