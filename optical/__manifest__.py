{
    'name': 'Optique',
    'version': '18.0.6.0.0',
    'category': 'Optique/Core',
    'summary': 'Gestion optique avec facturation assurance',
    'description': """
Module de gestion optique
=========================

Gestion complète d'un magasin d'optique :
* Sécurité par rôle (vendeur / responsable)
* Menus opérationnels et configuration
* Multi-boutiques optionnel via le module bridge optical_operating_unit
    """,
    'author': 'Otiten',
    'website': 'https://www.otiten.com',
    'license': 'LGPL-3',
    'depends': [
        'sale_management',
        'contacts',
        'account',
        'product_brand',
    ],
    'external_dependencies': {
        'python': ['num2words'],
    },
    'data': [
        'data/optical_groups.xml',
        'data/optical_sequence.xml',
        'data/optical_cron.xml',
        'data/ir_sequence_data.xml',
        'data/mail_template_pec.xml',
        'security/ir.model.access.csv',
        'security/optical_security.xml',
        'views/res_partner_views.xml',
        'views/optical_prescription_views.xml',
        'views/optical_insurer_plan_views.xml',
        'views/optical_coverage_rule_views.xml',
        'views/optical_policy_views.xml',
        'views/sale_order_views.xml',
        'views/optical_pec_views.xml',
        'views/account_move_views.xml',
        'views/optical_attribute_views.xml',
        'views/product_template_views.xml',
        'report/report_claim_sheet.xml',
        'report/optical_sale_report_views.xml',
        'views/optical_claim_sheet_views.xml',
        'wizard/claim_sheet_wizard_views.xml',
        'views/optical_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'optical/static/src/js/optical_diopter_widget.js',
            'optical/static/src/js/optical_diopter_widget.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
}
