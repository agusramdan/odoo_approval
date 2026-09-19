# -*- coding: utf-8 -*-
{
    'name': "Delegation of Authority (DoA) Configuration",
    'summary': """
        Delegation of Authority (DoA) Configuration
        """,
    'description': """
        This module config a feature for Delegation of Authority (DOA).
        It allows users to delegate authority form access.
    """,
    'author': "Agus Muhammad Ramdan",
    'website': "http://www.yourcompany.com",
    'category': 'Security & Access Rights',
    'version': '13.0.0.0.3',
    # any module necessary for this one to work correctly
    'depends': ['base', 'mail', 'antareja_base'],
    # always loaded
    'data': [
        #'data/user_delegate_cron.xml',
        #'data/user_delegate_sequence.xml',

        #'security/base_groups.xml',
        #'security/ir.model.access.csv',

        #'views/user_delegation_views.xml',
        #'views/approval_audit_log_views.xml',
        #'views/res_config_settings_views.xml',
        'views/menuitem_views.xml',
    ],
}
