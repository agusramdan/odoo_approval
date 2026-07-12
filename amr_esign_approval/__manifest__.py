# -*- coding: utf-8 -*-

{
    'name': "E-Sign || Approval",
    'summary': "Add Feature Approval Task",
    'description': " ",
    'author': "Agus Muhammad Ramdan",
    'website': "http://www.yourcompany.com",
    'category': 'Uncategorized',
    'version': '13.0.0.0.0',
    'depends': ['base', 'mail', 'amr_approval', 'amr_esign_pdf'],
    'data': [

        'views/approval_views.xml',
        'views/menuitem_views.xml',

        'data/notification_template_approval.xml',
        'data/approval_template_data.xml',
    ],
}
