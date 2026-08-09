# -*- coding: utf-8 -*-
{
    'name': "Approval Aggregation",
    'version': '13.0.1.0.0',
    'depends': ['base', 'web', 'amr_resource'],
    'website': "",
    'description': "Approval Aggregation for multiple instance",
    'data': [
        'security/res_groups.xml',
        'security/ir_rule.xml',
        'security/ir.model.access.csv',

        'views/approval_task_aggregator_views.xml',
        'views/approval_task_request_views.xml',

        'views/menuitem.xml',
    ],
}
