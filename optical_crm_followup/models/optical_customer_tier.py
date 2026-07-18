# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class OpticalCustomerTier(models.Model):
    """Tier client configurable (Story 18-1 — refonte du VIP figé).

    Remplace la ``Selection`` ``standard``/``vip`` de la V1 (Story 17-1) par
    un modèle paramétrable en UI : un responsable peut créer/éditer ses
    paliers (nom, rang, seuil de CA, étapes réservées) sans intervention
    développeur (NFR-11).

    Propriétés conservées de la V1 (raison du modèle dédié, PAS des tags
    ``res.partner.category`` — cf. Dev Notes décision 1) :
      - calcul automatique par CA cumulé (``threshold_fcfa``)
      - exclusivité : un seul tier par client (Many2one sur res.partner)
      - sémantique de seuil ordonnée (``sequence``)
    """

    _name = 'optical.customer.tier'
    _description = "Tier client (fidélisation optique)"
    _order = 'sequence, id'

    name = fields.Char(
        string="Nom du tier",
        required=True,
        translate=True,
    )
    sequence = fields.Integer(
        string="Rang",
        default=10,
        help="Ordre / rang du tier : plus la valeur est élevée, plus le tier "
             "est « premium ». Sert à la sémantique cumulative d'injection "
             "d'étapes (un tier supérieur hérite des attentions des tiers "
             "inférieurs — Story 18-1 AC-4.2).",
    )
    threshold_fcfa = fields.Float(
        string="Seuil CA (FCFA, TTC)",
        default=0.0,
        help="CA cumulé (TTC) des commandes confirmées au-delà duquel ce tier "
             "s'applique automatiquement. Le tier par défaut ignore ce seuil "
             "(il s'applique quand aucun autre tier n'est atteint). Un seuil "
             "≤ 0 sur un tier non-défaut est ignoré au calcul (Story 18-1 "
             "AC-5.2). ATTENTION : modifier un seuil déclenche le recalcul "
             "des tiers de tous les clients (peut prendre quelques secondes).",
    )
    active = fields.Boolean(default=True)
    is_default = fields.Boolean(
        string="Tier par défaut",
        help="Tier attribué à un client tant qu'aucun seuil n'est atteint "
             "(remplace l'ancien « standard »). Exactement un tier doit être "
             "marqué par défaut (Story 18-1 AC-1.3).",
    )
    color = fields.Integer(
        string="Couleur",
        help="Couleur du badge affiché sur la fiche client et dans le "
             "reporting.",
    )
    code = fields.Char(
        string="Code technique",
        help="Clé technique stable, optionnelle, pour référencer le tier "
             "depuis des données ou du code (ex. ``standard``, ``vip``). "
             "Non affiché au client.",
    )

    _sql_constraints = [
        (
            'code_uniq',
            'unique(code)',
            "Le code technique d'un tier doit être unique.",
        ),
    ]

    # ------------------------------------------------------------------
    # Contrainte : exactement un tier par défaut (AC-1.3)
    # ------------------------------------------------------------------

    @api.constrains('is_default', 'active')
    def _check_single_default(self):
        """Story 18-1 AC-1.3 — exactement un tier ``is_default`` actif.

        La contrainte est vérifiée globalement (pas seulement sur ``self``)
        car poser ``is_default`` sur un tier ou désactiver le tier défaut
        impacte l'invariant sur l'ensemble de la table.
        """
        defaults = self.search([('is_default', '=', True), ('active', '=', True)])
        if len(defaults) > 1:
            raise ValidationError(_(
                "Un seul tier client peut être marqué « par défaut ». "
                "Tiers en conflit : %(names)s.",
                names=", ".join(defaults.mapped('name')),
            ))
        # 0 tier par défaut est toléré uniquement s'il n'existe aucun tier
        # actif (module en cours d'installation / table vide), ou pendant le
        # basculement atomique du défaut (``action_set_as_default`` retire
        # l'ancien défaut AVANT de poser le nouveau — état transitoire à 0).
        # Dès qu'un tier actif existe hors de ce basculement, l'un d'eux DOIT
        # être le défaut.
        if (
            not defaults
            and not self.env.context.get('optical_tier_switching_default')
            and self.search_count([('active', '=', True)])
        ):
            raise ValidationError(_(
                "Un tier client doit être marqué « par défaut » (celui "
                "attribué aux clients n'atteignant aucun seuil)."
            ))

    def action_set_as_default(self):
        """Story 18-1 AC-1.3 (revue 2026-07-18, M2) — bascule atomique du défaut.

        La contrainte ``_check_single_default`` (stricte : ni 0 ni ≥2) rendait
        impossible de changer le tier par défaut via la liste éditable (toute
        écriture intermédiaire violait l'invariant). Ce bouton effectue le
        basculement en un seul geste :
          1. retrait du flag sur l'ancien défaut (état transitoire à 0 toléré
             via le contexte ``optical_tier_switching_default``) ;
          2. pose du flag sur ``self`` → état final à exactement 1 défaut,
             validé normalement.

        Réservé aux managers par l'ACL (write sur ``optical.customer.tier``).
        """
        self.ensure_one()
        if self.is_default:
            return
        others = self.search([
            ('is_default', '=', True), ('id', '!=', self.id),
        ])
        if others:
            others.with_context(
                optical_tier_switching_default=True,
            ).write({'is_default': False})
        self.write({'is_default': True})

    # ------------------------------------------------------------------
    # Recompute des partners impactés par un changement de config tier
    # ------------------------------------------------------------------

    _TIER_COMPUTE_TRIGGER_FIELDS = frozenset({
        'threshold_fcfa', 'sequence', 'active', 'is_default',
    })

    def _trigger_partner_tier_recompute(self):
        """Recalcule ``optical_customer_tier_id`` de tous les partners.

        Story 18-1 AC-2.4 (option a) — le compute du tier sur ``res.partner``
        ne peut pas dépendre via ``@api.depends`` d'un champ d'un autre modèle
        (le seuil du tier) sans relation inverse matérialisée. On déclenche
        donc explicitement le recompute depuis un ``write`` sur le tier
        lorsqu'un champ structurant change (seuil, rang, activation, défaut).

        En mono-company Luxe Optique le volume de partners reste modéré ; le
        recompute batch (1 search tiers + 1 read_group SO) reste O(1) requêtes.

        Pendant l'installation / mise à jour du module (``registry`` non
        « ready »), on s'abstient : le chargement des données puis le script
        post-migration se chargent d'une population unique et cohérente —
        éviter les recomputes en rafale à chaque record de tier chargé.
        """
        if not self.env.registry.ready:
            return
        Partner = self.env['res.partner'].sudo()
        partners = Partner.search([])
        if partners:
            partners._compute_optical_customer_tier()
            # Persister immédiatement : le compute assigne dans le cache ; sans
            # flush, une invalidation ultérieure (ou une lecture concurrente)
            # perdrait la nouvelle valeur du champ stocké.
            partners.flush_recordset(['optical_customer_tier_id'])

    def write(self, vals):
        res = super().write(vals)
        if self._TIER_COMPUTE_TRIGGER_FIELDS.intersection(vals):
            self._trigger_partner_tier_recompute()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        tiers = super().create(vals_list)
        # Un nouveau tier (avec seuil) peut faire basculer des clients
        # existants — recompute défensif.
        tiers._trigger_partner_tier_recompute()
        return tiers
