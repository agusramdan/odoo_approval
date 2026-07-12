# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    module_amr_hr_employee_hierarchy = fields.Boolean(string="Approval Employee Hierarchy")
    module_amr_hr_employee_delegation = fields.Boolean(string="Approval Employee Delegation")
    module_amr_hr_job_position = fields.Boolean(string="Approval Job Position")

    module_amr_doa_approval = fields.Boolean(string="DOA Approval")
    module_amr_doa_activate = fields.Boolean(string="Activate DOA Approval")

    module_amr_approval_mobile_client = fields.Boolean(string="Mobile Client")
