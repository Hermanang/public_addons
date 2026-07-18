# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Fenêtre pour la sous-métrique « désabonnement rapide » (Story 17-2 AC-4.4).
_FAST_UNSUBSCRIBE_WINDOW_DAYS = 30


class OpticalFollowupPlan(models.Model):
    _name = 'optical.followup.plan'
    _description = "Plan-type de suivi client optique"
    _order = 'sequence, id'

    name = fields.Char(string="Nom du plan", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    duration_months = fields.Integer(
        string="Durée (mois)",
        help="Métadonnée informative — durée totale couverte par le plan.",
    )
    optical_type_trigger = fields.Selection(
        [
            ('any', "Tous types (fallback)"),
            ('unifocal', "Unifocal"),
            ('progressive', "Progressif"),
            ('lentilles', "Lentilles de contact"),
        ],
        string="Déclencheur produit",
        default='any',
        required=True,
        help="Clé de sélection FR-02 : le plan est appliqué si la commande "
             "contient un produit correspondant. 'any' est le fallback par défaut.",
    )
    tier_id = fields.Many2one(
        'optical.customer.tier',
        string="Tier réservé",
        ondelete='restrict',
        index=True,
        help="Story 18-1 AC-4 — si renseigné, ce plan n'est PAS sélectionné "
             "par FR-02 (``_select_for_sale_order``) : ses étapes sont "
             "injectées en supplément pour les clients atteignant ce tier "
             "(sémantique cumulative — un tier supérieur reçoit aussi les "
             "attentions des tiers inférieurs). Vide = plan universel "
             "(comportement des presets principaux).",
    )
    step_ids = fields.One2many(
        'optical.followup.plan.step',
        'plan_id',
        string="Étapes",
    )
    fast_unsubscribe_rate_30d_display = fields.Char(
        string="Taux désabonnement 30 j",
        compute='_compute_fast_unsubscribe_rate_30d_display',
        store=False,
        help="Sous-métrique FR-23 (Story 17-2 AC-4.4) : proportion de "
             "clients ayant opt-out dans les 30 j suivant leur 1ʳᵉ relance, "
             "sur l'ensemble des clients ayant reçu une 1ʳᵉ relance dans la "
             "période. Affiche '—' si aucun 1ᵉʳ contact sur la période. "
             "Rate calculé toutes boutiques confondues pour ce plan.",
    )

    @api.depends('active')
    def _compute_fast_unsubscribe_rate_30d_display(self):
        """Story 17-2 AC-4.4 — taux désabonnement rapide 30 j par plan.

        Formule : ``count(partners with (optout_date - first_contact_date)
        <= 30 j) / count(partners with first_contact_date != NULL in period)``.

        Batch-safe (revue M1 S17-2) : UNE seule ``search`` sur
        ``optical.followup.schedule`` pour tous les plans self, puis dispatch
        Python. Précédent : 1 search par plan (N+1). ``@api.depends('active')``
        est un dep « faible » — le compute ne se re-déclenche pas
        automatiquement à chaque nouveau schedule/opt-out ; recalcul à chaque
        ``read`` du champ (compute non-stored).
        """
        if not self:
            return
        Schedule = self.env['optical.followup.schedule'].sudo()
        today = fields.Date.today()
        window_start = fields.Date.subtract(today, days=_FAST_UNSUBSCRIBE_WINDOW_DAYS)
        # 1 seule requête pour tous les plans self
        all_schedules = Schedule.search([
            ('plan_id', 'in', self.ids),
            ('first_contact_date', '!=', False),
            ('first_contact_date', '>=', window_start),
        ])
        by_plan = {}
        for schedule in all_schedules:
            by_plan.setdefault(schedule.plan_id.id, []).append(schedule)
        for plan in self:
            schedules = by_plan.get(plan.id, [])
            if not schedules:
                plan.fast_unsubscribe_rate_30d_display = '—'
                continue
            unsub = 0
            for schedule in schedules:
                partner = schedule.partner_id
                if (
                    partner.optical_followup_optout_date
                    and (
                        partner.optical_followup_optout_date
                        - schedule.first_contact_date
                    ).days <= _FAST_UNSUBSCRIBE_WINDOW_DAYS
                ):
                    unsub += 1
            rate = 100.0 * unsub / len(schedules)
            plan.fast_unsubscribe_rate_30d_display = "%.0f %%" % rate

    # ------------------------------------------------------------------
    # Sélection du preset applicable à une sale.order (FR-02)
    # ------------------------------------------------------------------

    @api.model
    def _select_for_sale_order(self, sale_order):
        """Retourne le plan applicable pour une sale.order selon FR-02.

        Priorité : ``lentilles`` > ``progressive`` > fallback ``any``.
        Retourne un recordset vide si aucun plan actif ne matche
        (log warning au niveau appelant).
        """
        if not sale_order or not sale_order.order_line:
            return self._find_active_plan('any')

        templates = sale_order.order_line.mapped('product_id.product_tmpl_id')

        has_contact_lens = any(t.optical_type == 'contact_lens' for t in templates)
        if has_contact_lens:
            plan = self._find_active_plan('lentilles')
            if plan:
                return plan

        has_progressive = any(
            t.optical_type == 'lens' and t.lens_design == 'progressive'
            for t in templates
        )
        if has_progressive:
            plan = self._find_active_plan('progressive')
            if plan:
                return plan

        return self._find_active_plan('any')

    @api.model
    def _find_active_plan(self, trigger):
        """Cherche le plan actif dont ``optical_type_trigger == trigger``.

        Retourne le premier trouvé (ordonné par ``sequence, id``), ou un
        recordset vide si aucun match.

        Story 18-1 AC-4.2 — les plans réservés à un tier (``tier_id`` non
        vide) NE DOIVENT JAMAIS être sélectionnés par FR-02 : leurs étapes
        sont injectées en supplément par ``_inject_tier_steps``. On les exclut
        donc du domaine via ``tier_id = False`` (remplace l'ancienne exclusion
        par XML ID de ``plan_vip_extra``).
        """
        domain = [
            ('active', '=', True),
            ('optical_type_trigger', '=', trigger),
            ('tier_id', '=', False),
        ]
        return self.search(domain, limit=1)


class OpticalFollowupPlanStep(models.Model):
    _name = 'optical.followup.plan.step'
    _description = "Étape d'un plan-type de suivi"
    _order = 'plan_id, sequence, id'

    plan_id = fields.Many2one(
        'optical.followup.plan',
        string="Plan",
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Nom de l'étape", required=True)
    offset_days = fields.Integer(
        string="Décalage (jours)",
        required=True,
        default=30,
        help="Jours ajoutés à delivered_date pour calculer date_planned.",
    )
    activity_type_id = fields.Many2one(
        'mail.activity.type',
        string="Type d'activité",
        required=True,
        ondelete='restrict',
    )
    suggested_channel = fields.Selection(
        [
            ('email', "Email"),
            ('whatsapp', "WhatsApp"),
            ('call', "Appel téléphonique"),
            ('in_person', "Visite en boutique"),
        ],
        string="Canal recommandé",
    )
    suggested_role = fields.Selection(
        [
            ('optician', "Opticien"),
            ('advisor', "Conseiller / Commercial"),
            ('manager', "Responsable"),
        ],
        string="Rôle recommandé",
    )
    objective = fields.Char(
        string="Objectif",
        help="Injecté dans mail.activity.summary lors de la matérialisation.",
    )
    description = fields.Text(
        string="Description",
        help="Injecté dans mail.activity.note (avec canal + rôle recommandés).",
    )
    mail_template_id = fields.Many2one(
        'mail.template',
        string="Template mail suggéré",
        ondelete='set null',
        help="Optionnel — proposé au commercial dans la note d'activité.",
    )
    birthday_step = fields.Boolean(
        string="Étape anniversaire",
        help="Étape dont la ``date_planned`` est calculée dynamiquement à "
             "partir de ``partner.birthdate`` (prochaine occurrence après "
             "``delivered_date``, repli 28-02 pour un anniversaire 29-02). "
             "Orthogonal au tier (pilote le calcul de date, pas "
             "l'appartenance). Utilisé par ``_inject_tier_steps`` — "
             "Story 18-1 AC-4.",
    )
