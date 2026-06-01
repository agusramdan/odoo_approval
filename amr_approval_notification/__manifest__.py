# -*- coding: utf-8 -*-
{
    'name': 'Approval Notification Integration',
    'category': 'Tools',
    'description': "Glue module to integrate approval system with notification system, especially for digital "
                   "signature notification",
    'author': 'Agus Muhammad Ramdan',
    'depends': ['base', 'web', 'amr_approval', 'amr_notification'],
    'data': [
        'views/notification_log_views.xml',
    ],
    'license': 'LGPL-3',
}
