# -*- coding: utf-8 -*-
{
    'name': 'OTN Création et synchronisation des filtres produits',
    'version': '18.0.0.0',
    'category': 'Website',
    'summary': 'Ce code met automatiquement à jour ou crée les filtres produits',
    'description': '''
    
    Ce code met automatiquement à jour ou crée les filtres produits (product.filter) et 
    leurs valeurs (product.filter.value) à chaque création ou modification d'un produit, en 
    fonction des champs dynamiques définis dans filter.field.

    ''',
    'author': 'OTN',
    'website':'',
    'depends': ['base', 'sale_management', 'product', 'bi_website_shop_product_filter', 'otn_optical'],
    'data': [
        'security/ir.model.access.csv',
        'data/default_filter_data.xml',
        'views/homepage.xml',
        'data/website_data.xml',
        'views/filter_field_views.xml',
    ],
    'auto_install': False,
    'installable': True,
    'post_init_hook': 'post_init_hook',
}
