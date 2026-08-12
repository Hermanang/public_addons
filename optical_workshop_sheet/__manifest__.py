{
    'name': 'Optique - Fiche de montage',
    'version': '18.0.3.0.0',
    'category': 'Optique/Bridge',
    'summary': "Fiche de montage A4 pour l'atelier (devis d'optique)",
    'description': """
Fiche de montage pour devis Optique
====================================

Ajoute une action d'impression "Fiche de montage" sur les devis (sale.order),
au format A4, destinée à l'atelier de montage :

* Logo + coordonnées boutique (adresse dynamique via warehouse.partner_id)
* Bloc client : Prénom/Nom + Tél
* Meta : Dossier, Date commande, Date livraison, Vendeur, Boutique
* Section Monture achetée :
  - Marque + Référence
  - Type de verres (3 cases : loin/près/progressifs) — depuis prescription.vision_type
  - Traitement des verres (checkboxes dynamiques depuis référentiel
    optical.lens.treatment, cochées si présent sur snapshot verre S19-5)
  - EP / EP OD / EP OG (écart pupillaire)
  - Tableau OD/OG × SPH/CYCL/AXE/ADD/PRISME/BASE
  - Tableau HBOX/VBOX/DBL/FH/PANTO/VERTEX/Base Curve — HBOX + DBL auto-remplis
    depuis lens_width / bridge_width de la fiche monture, autres cases vides
* Section Monture offerte (identique, si lignes is_gift)
* Bloc paiements auto :
  - Prix (amount_total)
  - Règlement 1 / Règlement 2 (les 2 premiers paiements postés)
  - Assurance/IPM (nom assureur), Part assurance, Reste (résiduel patient)
* Note libre
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
        'report/optical_workshop_sheet.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
