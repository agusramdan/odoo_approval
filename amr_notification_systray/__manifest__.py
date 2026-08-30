# -*- coding: utf-8 -*-
{
    'name': 'Notification Bus',
    'version': '13.0.1.0.0',
    'category': 'Tools',
    'summary': 'Notifications Bus for Odoo ',
    'description': 'Notifications Bus for Odoo 13.0.',
    'author': 'Agus',
    'website': 'https://agus.ramdan.tech',
    'license': 'LGPL-3',
    'depends': ['base','mail', 'bus', 'web', 'amr_notification'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        "views/notification_partner_views.xml",
        "views/assets.xml",
    ],
    "qweb": [
        "static/src/xml/notification_systray.xml",
    ],

    'demo': [],
    'assets': {},
    'installable': True,
    'auto_install': False,
    'application': False,
}
