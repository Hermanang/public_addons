{
    'name': 'Optique Exclusion cadeaux/promos',
    'version': '18.0.1.1.0',
    'category': 'Optique/Bridge',
    'summary': 'Case à cocher Cadeau sur lignes SO, exclusion du bordereau assurance',
    'author': 'Otiten',
    'website': 'https://www.otiten.com',
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
