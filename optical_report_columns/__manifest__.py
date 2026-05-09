{
    'name': 'Optique Colonnes dynamiques bordereau',
    'version': '18.0.1.0.0',
    'category': 'Optique/Bridge',
    'summary': 'Bridge colonnes dynamiques pour le bordereau optique',
    'description': """
Bridge Colonnes Dynamiques — Bordereau Optique
================================================

Connecte le module générique report_dynamic_columns au bordereau
mensuel optique :
* Colonnes configurables pour le bordereau (claim sheet)
* Presets par type d'assureur (assurance / IPM)
* Sélection des colonnes dans le wizard avant génération
* Traçabilité des colonnes utilisées sur le bordereau
""",
    'author': 'Otiten',
    'website': 'https://www.otiten.com',
    'license': 'LGPL-3',
    'depends': [
        'report_dynamic_columns',
        'optical',
    ],
    'data': [
        'data/claim_sheet_columns.xml',
        'data/paperformat.xml',
        'views/claim_sheet_wizard_views.xml',
        'report/report_claim_sheet.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
