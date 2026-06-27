# -*- coding: utf-8 -*-

{
    'name': 'Approval Mobile Integration',
    'version': '13.0.1.0.0',
    "category": "Extra Tools",
    "license": "LGPL-3",
    'author': "Agus Muhammad Ramdan",
    'description': "Client connect to mobile application",
    'depends': ['base', 'mail', 'amr_approval', 'amr_service_client'],
    'data': [
        'security/ir.model.access.csv',
        'views/mobile_approval_views.xml',
        'views/mobile_notification_views.xml',
        'views/menuitem.xml',
        'views/res_config_settings_views.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False
}
