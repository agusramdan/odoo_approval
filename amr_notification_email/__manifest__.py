# -*- coding: utf-8 -*-
{
    'name': 'Notification Whatsapp',
    'version': '13.0.1.0.0',
    'category': 'Tools',
    'summary': 'WhatsApp notifications for Odoo partners',
    'description': 'Adds WhatsApp notification support for notification partners and integrates with an external WhatsApp API.',
    'author': 'Agus',
    'website': 'https://www.example.com',
    'license': 'LGPL-3',
    'depends': ['base', 'amr_notification'],
    'data': [
        'security/ir.model.access.csv',
        'views/notification_partner_views.xml',
        'views/notification_whatsapp_views.xml',
        'views/menuitem.xml',
    ],
    'demo': [],
    'assets': {},
    'installable': True,
    'auto_install': False,
    'application': False,
    'external_dependencies': {'python': ['requests']},
}
