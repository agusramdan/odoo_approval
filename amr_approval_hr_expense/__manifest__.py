# -*- coding: utf-8 -*-
{
    'name': "Approval HR Expense",
    'summary': "Add Feature Approval",
    'description': """ """,
    'author': "Agus Muhammad Ramdan",
    'website': "http://www.yourcompany.com",
    'category': 'Uncategorized',
    'version': '13.0.1.0.0',
    'depends': ['base', 'mail', 'hr', 'hr_expense', 'amr_approval', 'amr_approval_hr'],
    'data': [
        'data/approval_document_data.xml',
        'data/approval_template_data.xml',

        'views/approval_views.xml',
    ],
}
