{
    'name': 'Optique Operating Unit',
    'version': '18.0.1.0.0',
    'category': 'Optique/Bridge',
    'summary': 'Bridge Operating Unit pour le module Optique multi-boutiques',
    'description': """
Bridge Operating Unit — Optique
================================

Ajoute le support multi-boutiques (Operating Unit) au module Optique :
* Champs operating_unit_id sur les modèles optiques
* Record rules par unité opérationnelle
* Filtres et groupements OU dans les vues
* Menu de configuration des unités opérationnelles
    """,
    'author': 'Otiten',
    'website': 'https://www.otiten.com',
    'license': 'LGPL-3',
    'depends': [
        'optical',
        'operating_unit',
        'account_operating_unit',
        'sale_operating_unit',
        'stock_operating_unit',
        'sale_stock_operating_unit',
        'operating_unit_access_all',
        'report_qweb_operating_unit',
    ],
    'data': [
        'security/optical_ou_security.xml',
        'views/optical_prescription_views.xml',
        'views/optical_policy_views.xml',
        'views/optical_insurer_plan_views.xml',
        'views/optical_pec_views.xml',
        'views/account_move_views.xml',
        'views/optical_claim_sheet_views.xml',
        'views/optical_sale_report_views.xml',
        'views/optical_menus.xml',
        'report/report_claim_sheet.xml',
        'wizard/claim_sheet_wizard_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
