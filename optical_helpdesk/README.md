# Optique Helpdesk

Module de gestion des **réclamations client** pour les boutiques d'optique : motifs multi-cochables, diagnostic interne, rapport A5 double-volet conforme au PDF de référence.

## Fonctionnalités

- **Taxonomie 2D** : axe `type_id` (process : Réclamation / SAV / Renseignement) × axe `category_id` (topic : Optique / Service)
- **Champs métier optique** appliqués uniquement aux tickets de type Réclamation :
  - `product_id` filtré par les commandes liées (`sale_order_ids`)
  - `optical_type` (related sur `product_id.product_tmpl_id.optical_type`)
  - `purchase_price` auto-rempli depuis la ligne SO
  - `complaint_motive_ids` m2m vers `helpdesk.complaint.motive` (14 motifs seedés)
  - `cause_identified` Selection (Atelier / Manipulation client / Fournisseur / Autre)
  - `proposed_solution`, `refund_amount`, `internal_diagnostic`
- **Séquence dédiée** : `TR2026-XXXX` pour les Réclamations, séquence native helpdesk_mgmt (`HT00000`) pour les autres types
- **Rapport QWeb A5 portrait** double-volet (haut = client, bas = interne avec diagnostic)
- **Validation UTF-8** pour wkhtmltopdf via override `_build_wkhtmltopdf_args`

## Dépendances

- `helpdesk_mgmt` (OCA)
- `helpdesk_mgmt_sale` (OCA)
- `helpdesk_type` (OCA)
- `optical` (module métier optique du projet)
- `sale`

## Installation

```bash
docker compose run --rm odoo bash -c "odoo -d <db> -i optical_helpdesk --stop-after-init"
```

Une fois installé, configurer manuellement via UI :

1. **Helpdesk → Configuration → Teams** : créer une équipe par boutique (VDN, Corniche, etc.) et associer les types autorisés
2. **Helpdesk → Configuration → Channels** : créer les canaux (Boutique, Téléphone, WhatsApp, E-mail)
3. **Helpdesk → Configuration → Motifs réclamation** : ajuster la liste seedée de 14 motifs si besoin

## Tests

```bash
make test-helpdesk
# ou
docker compose run --rm odoo bash -c "odoo -d odoo_test -i optical,optical_helpdesk --test-tags /optical_helpdesk --stop-after-init --without-demo all"
```

## Compagnon optionnel

- `helpdesk_type_stage_validation` (présent dans `extra-addons/`) — bridge permettant de filtrer la validation des champs par stage selon le type. À installer manuellement si besoin (ex: forcer `proposed_solution` à la clôture **uniquement pour Réclamation**).

## Auteur

Otiten — https://www.otiten.com
