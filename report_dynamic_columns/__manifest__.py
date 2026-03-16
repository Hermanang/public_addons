# -*- coding: utf-8 -*-
{
    'name': 'Colonnes dynamiques de rapport',
    'version': '18.0.1.0.0',
    'category': 'Reporting',
    'summary': 'Colonnes configurables pour les rapports QWeb PDF',
    'description': """
Colonnes dynamiques de rapport
===============================

Module generique permettant de definir des colonnes configurables
pour les rapports QWeb PDF :
* Modele de colonnes avec type, alignement et sequence
* Profils de colonnes par type de rapport
* Mixin pour integration dans les rapports existants
* Template QWeb partiel reutilisable
    """,
    'author': 'Odoo Optic CE',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/report_dynamic_column_views.xml',
        'views/report_dynamic_column_profile_views.xml',
        'report/report_dynamic_table_template.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
