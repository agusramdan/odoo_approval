# -*- coding: utf-8 -*-
{
    'name': "Approval Account",
    'summary': "Add Feature Approval",
    'description': """ """,

    'author': "Agus Muhammad Ramdan",
    'website': "http://www.yourcompany.com",

    'category': 'Uncategorized',
    'version': '13.0.1.0.0',
    'depends': ['base', 'mail', 'account', 'amr_approval'],

    # always loaded
    'data': [
        'data/approval_template_data.xml',

        'views/approval_views.xml',
    ],
}
