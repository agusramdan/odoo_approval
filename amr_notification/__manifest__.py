# -*- coding: utf-8 -*-

{
    'name': 'Notification',
    'version': '13.0.0.0.0',
    'summary': "Notification",
    'category': 'Tools',
    'author': 'Agus',
    'depends': ['base', 'mail', 'auth_jwt', 'amr_mobile', 'amr_resource', ],
    'data': [
        'security/ir.model.access.csv',

        'views/notification_partner_views.xml',
        'views/notification_topic_views.xml',
        'views/res_config_settings_views.xml',

        'views/menuitem.xml',
    ],
    'installable': True,
    'application': False,
}
