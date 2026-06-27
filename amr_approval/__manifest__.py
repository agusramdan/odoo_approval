# -*- coding: utf-8 -*-

{
    'name': "Approval Task and Assignment",
    'summary': """Approval Task""",
    'description': """
        This addons contain 
        1. Notification for Approval Task
        2. Task Approval
        3. Assignment delegation or reassignment 
    """,
    'author': "Agus Muhammad Ramdan",
    'website': "http://agus.ramdan.tech",
    'category': 'Tools',
    'version': '13.0.0.1.1',
    'depends': ['base', 'base_setup', 'mail'],
    'data': [
        'security/base_groups.xml',
        'security/ir.model.access.csv',

        'data/ir_cron.xml',
        'data/ir_sequence.xml',

        'views/notification_template_views.xml',
        'views/notification_log_views.xml',

        'views/approval_audit_log_views.xml',
        'views/approval_task_views.xml',
        'views/approval_task_line_views.xml',
        'views/approval_template_views.xml',
        'views/approval_instance_views.xml',
        'views/approval_task_assignment_history_views.xml',
        'views/approval_matrix_rule_views.xml',
        'views/user_delegation_views.xml',
        'views/res_config_settings_views.xml',
        'views/menuitem.xml',
        'wizard/popup_reject.xml',
        'wizard/approval_task_line_assignment.xml',
        'wizard/rule_condition.xml',
    ],
    'demo': [],
    'installable': True,
}
