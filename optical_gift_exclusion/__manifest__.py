# -*- coding: utf-8 -*-
{
    'name': 'Optique — Exclusion cadeaux/promos',
    'version': '18.0.1.1.0',
    'category': 'Optique',
    'summary': 'Case a cocher Cadeau sur lignes SO, exclusion du bordereau assurance',
    'author': 'Odoo Optic CE',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['optical'],
    'data': [
        'views/sale_order_views.xml',
        'report/report_claim_sheet_inherit.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
