{
    'name': 'Optique - Reçu de caisse',
    'version': '18.0.1.0.0',
    'category': 'Optique/Bridge',
    'summary': "Reçu de caisse style ticket POS (80mm) pour les devis d'optique",
    'description': """
Reçu de caisse pour devis Optique
==================================

Ajoute une action d'impression "Reçu de caisse" sur les devis (sale.order),
inspirée du design des tickets POS (format 80mm monochrome) :

* Logo + coordonnées boutique
* Dossier (numéro devis), client, téléphone, dates, commercial, boutique
* Monture achetée + tableau SPH/CYL/AXE/ADD/PRISME/BASE
* Monture offerte (lignes is_gift) - section masquée si aucun cadeau
* Total TTC, Acompte (paiements enregistrés), Reste à payer
* Footer avec téléphone société et message de confiance
    """,
    'author': 'Luxe Optique',
    'license': 'LGPL-3',
    'depends': [
        'sale',
        'optical',
        'optical_gift_exclusion',
    ],
    'data': [
        'data/paperformat.xml',
        'report/optical_pos_receipt.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
