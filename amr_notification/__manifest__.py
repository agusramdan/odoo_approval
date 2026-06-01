# -*- coding: utf-8 -*-

{
    'name': 'Notification',
    'version': '13.0.0.0.0',
    'summary': "Notification Firebase",
    'category': 'Tools',
    'author': 'Agus',
    'depends': ['base', 'mail', 'auth_jwt', 'amr_mobile', 'amr_resource', 'amr_firebase'],
    'data': [
        'security/ir.model.access.csv',

        'views/notification_partner_views.xml',
    ],
    'installable': True,
    'application': False,
}
