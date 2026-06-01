# -*- coding: utf-8 -*-

{
    'name': 'Resource Server',
    'category': 'Tools',
    'description': "Allow users to validate access token and protect resources.",
    'maintainer': 'Agus Muhammad Ramdan',
    'depends': ['base', 'web', 'base_setup', ],
    'version': '13.0.0.0.1',
    'data': [
        'security/res_groups.xml',
        'views/res_config_settings_views.xml',
        'wizard/create_user_wizard.xml',
    ],
    'license': 'LGPL-3',
}
