# -*- coding: utf-8 -*-

{
    'name': 'Approval Demo',
    'version': '13.0.1.0.1',
    'category': 'Tools',
    'summary': 'Demo Approval  Odoo 13.',
    'description': 'Demo Approval.',
    'author': 'Auto Generated',
    'website': 'https://example.com',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'amr_approval'],
    'data': [
        'data/approval_template_data.xml',
        'data/approval_document_data.xml',

        'views/menuitems.xml',
    ],
    'demo': [],
    'assets': {},
    'installable': True,
    'auto_install': False,
    'application': False,
}
