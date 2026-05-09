{
    'name': 'Colonnes dynamiques de rapport',
    'version': '18.0.1.0.0',
    'category': 'Reporting',
    'summary': 'Colonnes configurables pour les rapports QWeb PDF',
    'description': """
Colonnes dynamiques de rapport
===============================

Module générique permettant de définir des colonnes configurables
pour les rapports QWeb PDF :
* Modèle de colonnes avec type, alignement et séquence
* Profils de colonnes par type de rapport
* Mixin pour intégration dans les rapports existants
* Template QWeb partiel réutilisable
    """,
    'author': 'Otiten',
    'website': 'https://www.otiten.com',
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
