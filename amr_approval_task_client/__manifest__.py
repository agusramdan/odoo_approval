# -*- coding: utf-8 -*-

{
    'name': 'Approval Aggregator Integration',
    'version': '13.0.1.0.0',
    "category": "Extra Tools",
    "license": "LGPL-3",
    'author': "Agus Muhammad Ramdan",
    'description': "Client connect to Aggregator application",
    'depends': ['base', 'mail', 'amr_resource', 'amr_approval', 'amr_service_client'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False
}
