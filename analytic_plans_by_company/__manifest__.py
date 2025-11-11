{
    'name': "Analytic Plans by Company",
    'version': "18.0.1.0.0",
    'depends': ['account'],
    'author': "Muhammad Wael",
    'category': 'Analytic Plan',
    'description': """
    Making company field for analytic plans to be seen by company_id only
    """,
    'license': 'LGPL-3',
    'data': [
        'views/inherit_account_analytic_plan.xml',
    ],
    'images': [
        'static/description/icon.png',        
        'static/description/cover.png',       
        'static/description/screenshot1.png',
        'static/description/screenshot2.png',
    ],

    'installable': True,
    'application': False,
    'auto_install': False,
}
