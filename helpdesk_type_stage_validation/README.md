# Helpdesk Type-aware Stage Validation

Bridge entre [`helpdesk_type`](https://github.com/OCA/helpdesk/tree/18.0/helpdesk_type) et [`helpdesk_mgmt_stage_validation`](https://github.com/OCA/helpdesk/tree/18.0/helpdesk_mgmt_stage_validation).

## Problème résolu

`helpdesk_mgmt_stage_validation` permet d'imposer que certains champs soient remplis avant qu'un ticket atteigne un stage donné. **Mais** la validation s'applique à **tous les tickets**, sans distinction de type.

Exemple problématique : si tu configures « Stage Clôturé requiert `proposed_solution` », ça s'applique aussi aux tickets `SAV` ou `Renseignement` — alors que ces types n'ont peut-être pas de `proposed_solution` à fournir.

## Solution

Ce module ajoute un champ `validate_type_ids` sur `helpdesk.ticket.stage` :

- **Vide** → la validation s'applique à tous les types (comportement par défaut helpdesk_mgmt_stage_validation)
- **Rempli** → la validation ne s'applique qu'aux tickets dont `type_id` est dans cette liste

## Cas d'usage

`Helpdesk → Configuration → Stages → Terminé` :

| Champ | Valeur |
|---|---|
| Fields to Validate | `Solution proposée` |
| Types concernés par la validation | `Réclamation` |

→ Réclamation à clôturer sans solution → erreur
→ SAV à clôturer sans solution → OK (skip)
→ Renseignement à clôturer sans solution → OK (skip)

## Implémentation technique

Override de `_check_ticket_has_empty_fields` sur `helpdesk.ticket` : si le stage cible a `validate_type_ids` non vide et que le `type_id` du ticket n'est pas dedans, retourne `False` (skip validation), sinon délègue au `super()`.

## Dépendances

- `helpdesk_mgmt_stage_validation` (OCA)
- `helpdesk_type` (OCA)

## Tests

```bash
docker compose run --rm odoo bash -c "odoo -d odoo_test -i helpdesk_type_stage_validation --test-tags /helpdesk_type_stage_validation --stop-after-init --without-demo all"
```

## Auteur

Otiten — https://www.otiten.com
