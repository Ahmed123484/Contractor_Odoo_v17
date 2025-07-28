# -*- coding: utf-8 -*-
{
    'name': 'Contractor Statements',
    'version': '1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Manage contractor statements and progress billing',
    'description': """
        Contractor Statements Management
        ===============================
        
        This module allows you to:
        * Create and manage contractor statements
        * Track work progress and quantities
        * Calculate financial amounts automatically
        * Generate sequential statement numbers based on project and work type
        * Track previous quantities automatically
        
        Features:
        * Automatic calculation of totals and progress percentages
        * Previous quantity tracking based on project, work type, and product
        * Financial calculations including retention, taxes, and deductions
        * Simple workflow with draft, confirmed, and approved states
    """,
    'author': 'Your Company',
    'depends': ['base', 'account', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'report/contractor_statement_report_template.xml',
        'report/contractor_statement_reports.xml',
        'views/contractor_statement_views.xml',
        'views/payment_method_views.xml',
        'views/contractor_analysis_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}