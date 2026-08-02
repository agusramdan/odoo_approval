# -*- coding: utf-8 -*-

{
    'name': "Approval || ESign",
    'summary': "Add Feature Approval Task",
    'description': " Add Feature Approval Task ",
    'author': "Agus Muhammad Ramdan",
    'website': "http://www.yourcompany.com",
    'category': 'Approval',
    'version': '13.0.0.0.0',
    'depends': ['base', 'mail', 'amr_approval', 'amr_esign_pdf'],
    'data': [
        'views/approval_instance_views.xml',
        'views/approval_document_views.xml',
    ],
}
