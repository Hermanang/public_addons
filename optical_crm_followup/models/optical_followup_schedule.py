# -*- coding: utf-8 -*-
import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.mail import plaintext2html

_logger = logging.getLogger(__name__)


def _next_birthday_occurrence(birthdate, ref_date):
    """Retourne la prochaine occurrence de ``birthdate`` STRICTEMENT après
    ``ref_date`` (Story 17-1 AC-5.2/AC-5.3).

    Contrat :
      - Anniversaire à venir dans l'année → renvoie cette occurrence
      - Anniversaire passé ou = ref_date → renvoie l'occurrence de l'année
        suivante (D-VIP-BIRTHDAY-SAMEDAY : le jour même est « passé »)
      - Anniversaire 29 février → repli 28 février en année non-bissextile
        (D-VIP-LEAP-YEAR ; ``dateutil.relativedelta`` gère nativement)

    Retourne ``None`` si ``birthdate`` est falsy (AC-6.1 — l'appelant skippe
    la ligne anniversaire).
    """
    if not birthdate:
        return None
    year = ref_date.year
    # Tentative d'occurrence cette année (relativedelta gère 29-02 → 28-02).
    candidate = birthdate + relativedelta(year=year)
    if candidate > ref_date:
        return candidate
    return birthdate + relativedelta(year=year + 1)


class OpticalFollowupSchedule(models.Model):
    _name = 'optical.followup.schedule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Calendrier de suivi client optique (instance)"
    _order = 'create_date desc, id desc'

    name = fields.Char(string="Référence", required=True, default="Nouveau")
    partner_id = fields.Many2one(
        'res.partner',
        string="Client",
        required=True,
        ondelete='restrict',
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string="Boutique",
        required=True,
        index=True,
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string="Commande d'origine",
        ondelete='restrict',
        help="SO ayant déclenché la création du calendrier au picking outgoing.",
    )
    picking_id = fields.Many2one(
        'stock.picking',
        string="Picking d'origine",
        ondelete='restrict',
    )
    plan_id = fields.Many2one(
        'optical.followup.plan',
        string="Plan-type appliqué",
        ondelete='restrict',
    )
    referent_user_id = fields.Many2one(
        'res.users',
        string="Commercial référent",
        ondelete='set null',
        help="Résolu à la création : partner.user_id si présent, sinon "
             "sale_order.user_id. Permet la réattribution (Story 3.3).",
    )
    delivered_date = fields.Date(
        string="Date de remise",
        help="Date réelle de la validation du picking outgoing (picking.date_done).",
    )
    pause_reason = fields.Selection(
        [
            ('sav_open', "SAV en cours"),
            ('majority_pending', "Majorité en attente"),
            ('manual', "Suspension manuelle"),
        ],
        string="Motif de suspension",
        help="Renseigné automatiquement à la mise en pause (15.2/16.2 pour "
             "'sav_open', 17-3 pour 'majority_pending', manuel pour 'manual').",
    )
    sav_paused_date = fields.Date(
        string="Date de mise en pause SAV",
        readonly=True,
        help="Horodatage précis du passage en pause pour motif 'sav_open' "
             "(audit R4 archi — sert au filtre de la vue supervision > 30 j). "
             "Conservé à la reprise pour reporting.",
    )
    sav_pause_duration_days = fields.Integer(
        string="Jours de pause SAV",
        compute='_compute_sav_pause_duration_days',
        store=False,
        help="Nombre de jours écoulés depuis la mise en pause SAV. "
             "Vaut 0 hors état paused/sav_open.",
    )
    first_contact_date = fields.Date(
        string="Date 1er contact effectif",
        readonly=True,
        index=True,
        help="Renseigné automatiquement à la 1ʳᵉ ligne 'done' (KPI 4 — Story 3.2). "
             "Indexé pour accélérer la sous-métrique désabonnement 30 j "
             "(Story 17-2 AC-4.4).",
    )
    state = fields.Selection(
        [
            ('running', "En cours"),
            ('paused', "Suspendu"),
            ('fulfilled', "Abouti"),
            ('cancelled', "Annulé"),
            ('expired', "Expiré"),
        ],
        string="État",
        default='running',
        required=True,
    )
    line_ids = fields.One2many(
        'optical.followup.schedule.line',
        'schedule_id',
        string="Étapes matérialisées",
    )
    steps_total_count = fields.Integer(
        string="Nombre total d'étapes",
        compute='_compute_steps_stats',
        store=False,
        help="Nombre total d'étapes matérialisées (line_ids). "
             "Sert au smart button de la form (Story 17-4).",
    )
    steps_done_count = fields.Integer(
        string="Étapes réalisées",
        compute='_compute_steps_stats',
        store=False,
        help="Nombre d'étapes en état 'done'. Sert au smart button (Story 17-4).",
    )
    next_step_date = fields.Date(
        string="Prochaine étape",
        compute='_compute_steps_stats',
        store=False,
        help="Date planifiée de la prochaine étape 'pending'/'overdue' "
             "(la plus ancienne). Sert à la kanban card. Faux si aucune "
             "étape à venir (Story 17-4).",
    )

    # ------------------------------------------------------------------
    # Reporting direction (Story 17-2) — KPI 2, 3, 4
    # ------------------------------------------------------------------

    # Monetary requiert un currency_id ; compute STORED (Odoo 18 graph model
    # exige que le currency_field d'une mesure Monetary soit persistant pour
    # supporter l'agrégation SQL — sans quoi Odoo lève « No aggregate function
    # has been provided ». Fallback company.currency_id si SO absente).
    currency_id = fields.Many2one(
        'res.currency',
        string="Devise",
        compute='_compute_currency_id',
        store=True,
        help="Devise du montant panier (Story 17-2 KPI 3). Suit sale_order_id "
             "si présent, sinon company.currency_id.",
    )
    overdue_line_count = fields.Integer(
        string="Lignes en retard",
        compute='_compute_overdue_line_count',
        store=False,
        help="Nombre de lignes 'overdue' du calendrier (KPI 2 — Story 17-2). "
             "Agrégeable par 'sum' en vue tree groupée.",
    )
    has_purchase_outcome = fields.Boolean(
        string="Rachat enregistré",
        compute='_compute_has_purchase_outcome',
        store=True,
        help="True si au moins une ligne a outcome='purchased'. Sert au "
             "filtre par défaut du KPI 3 (Story 17-2). Stored pour permettre "
             "le filtrage et le tri en graph view.",
    )
    amount_total_trigger_so = fields.Monetary(
        string="Panier déclenchement",
        compute='_compute_amount_total_trigger_so',
        store=True,
        currency_field='currency_id',
        aggregator='avg',
        help="Montant TTC de la SO ayant déclenché le calendrier (KPI 3 — "
             "Story 17-2). Faux si la SO d'origine a été unlinkée. Agrégé en "
             "moyenne dans le graph (panier moyen par commercial/boutique). "
             "STORED pour supporter l'agrégation SQL en graph view Odoo 18.",
    )
    amount_total_renewal_avg = fields.Monetary(
        string="Panier renouvellement moyen",
        compute='_compute_amount_total_renewal_avg',
        store=True,
        currency_field='currency_id',
        aggregator='avg',
        help="Moyenne des amount_total des sale.order postérieures du même "
             "partner (état sale/done, date_order > delivered_date). Zéro si "
             "aucune SO postérieure. KPI 3 — Story 17-2. Agrégé en moyenne "
             "dans le graph. STORED pour supporter l'agrégation SQL — recompute "
             "cascade sur les SO du partner (dep sale_order_ids.state/amount/"
             "date_order) : volume modeste V1 (~90 SO/mois total).",
    )
    contact_rate_30d_display = fields.Char(
        string="Taux de contact 30 j",
        compute='_compute_contact_rate_30d_display',
        store=False,
        help="Taux 'done / (done+overdue+unreachable)' calculé sur les lignes "
             "des 30 derniers jours de ce calendrier. Affiche '—' si aucune "
             "ligne éligible sur la période (KPI 1 — Story 17-2, MINEUR-5).",
    )
    email_open_rate_30d_display = fields.Char(
        string="Taux ouverture email 30 j",
        compute='_compute_email_open_rate_30d_display',
        store=False,
        help="Sous-métrique FR-22 (Story 17-2). Retourne '—' en V1 : Odoo CE "
             "sans mass_mailing ne track pas l'ouverture email transactionnel "
             "(D-KPI-EMAIL-TRACK). Colonne conservée pour prête V1.1.",
    )

    # ==================================================================
    # Compute (Story 16.2 — AC8)
    # ==================================================================

    @api.depends('line_ids.state', 'line_ids.date_planned')
    def _compute_steps_stats(self):
        """Story 17-4 — computes stored=False alimentant kanban + smart button.

        Trade-off assumé (H3 revue) : ``store=False`` implique un recalcul
        par record à chaque ``read`` sur ces champs. Volumes attendus
        faibles (< 1000 schedules, < 15 lignes/schedule) — pas d'impact
        perceptible. Contrepartie : ces champs ne peuvent être triés ni
        filtrés depuis les vues. Migrer à ``store=True`` si besoin futur.
        """
        for schedule in self:
            lines = schedule.line_ids
            schedule.steps_total_count = len(lines)
            schedule.steps_done_count = len(
                lines.filtered(lambda l: l.state == 'done')
            )
            upcoming = lines.filtered(
                lambda l: l.state in ('pending', 'overdue')
            )
            if upcoming:
                upcoming = upcoming.sorted('date_planned')
                schedule.next_step_date = upcoming[:1].date_planned
            else:
                schedule.next_step_date = False

    @api.depends('state', 'pause_reason', 'sav_paused_date')
    def _compute_sav_pause_duration_days(self):
        today = fields.Date.today()
        for schedule in self:
            if (
                schedule.state == 'paused'
                and schedule.pause_reason == 'sav_open'
                and schedule.sav_paused_date
            ):
                schedule.sav_pause_duration_days = (
                    today - schedule.sav_paused_date
                ).days
            else:
                schedule.sav_pause_duration_days = 0

    # ==================================================================
    # Reporting direction (Story 17-2) — computes KPI 2, 3, 4
    # ==================================================================

    @api.depends('sale_order_id', 'sale_order_id.currency_id')
    def _compute_currency_id(self):
        company_currency = self.env.company.currency_id
        for schedule in self:
            if schedule.sale_order_id and schedule.sale_order_id.currency_id:
                schedule.currency_id = schedule.sale_order_id.currency_id
            else:
                schedule.currency_id = company_currency

    @api.depends('line_ids.state')
    def _compute_overdue_line_count(self):
        for schedule in self:
            schedule.overdue_line_count = len(
                schedule.line_ids.filtered(lambda l: l.state == 'overdue')
            )

    @api.depends('line_ids.outcome')
    def _compute_has_purchase_outcome(self):
        for schedule in self:
            schedule.has_purchase_outcome = any(
                line.outcome == 'purchased' for line in schedule.line_ids
            )

    @api.depends('sale_order_id.amount_total')
    def _compute_amount_total_trigger_so(self):
        for schedule in self:
            schedule.amount_total_trigger_so = (
                schedule.sale_order_id.amount_total
                if schedule.sale_order_id else 0.0
            )

    @api.depends(
        'partner_id',
        'delivered_date',
        'partner_id.sale_order_ids.state',
        'partner_id.sale_order_ids.amount_total',
        'partner_id.sale_order_ids.date_order',
    )
    def _compute_amount_total_renewal_avg(self):
        """KPI 3 (Story 17-2 AC-3.2) — moyenne des SO postérieures du partner.

        Batch-safe : une seule ``search_read`` sur ``sale.order`` filtrée
        SQL sur ``date_order > min(eligible.delivered_date)`` pour couper le
        volume transféré Python (revue M8 S17-2). Puis dispatch par schedule
        avec filtrage fin ``dt > schedule.delivered_date`` en Python (chaque
        schedule a sa propre date de remise — pas de group_by unique SQL).

        Un partner sans SO postérieure retourne 0 (informationnel, cf. AC-3.2).
        """
        if not self:
            return
        eligible = self.filtered(
            lambda s: s.partner_id and s.delivered_date
        )
        rest = self - eligible
        for schedule in rest:
            schedule.amount_total_renewal_avg = 0.0

        partner_ids = eligible.mapped('partner_id').ids
        if not partner_ids:
            return

        # Revue M8 : cutoff SQL sur min(delivered_date) — évite de charger
        # tout l'historique SO d'un partner fidèle si le schedule le plus
        # ancien de self date de la semaine dernière.
        min_delivered = min(eligible.mapped('delivered_date'))
        SO = self.env['sale.order'].sudo()
        rows = SO.search_read(
            domain=[
                ('partner_id', 'in', partner_ids),
                ('state', 'in', ('sale', 'done')),
                ('date_order', '>', min_delivered),
            ],
            fields=['partner_id', 'amount_total', 'date_order'],
        )
        by_partner = {}
        for row in rows:
            pid = row['partner_id'][0] if row['partner_id'] else False
            if not pid:
                continue
            by_partner.setdefault(pid, []).append(
                (fields.Date.to_date(row['date_order']), row['amount_total'] or 0.0)
            )
        for schedule in eligible:
            entries = by_partner.get(schedule.partner_id.id, [])
            delivered = schedule.delivered_date
            posterior = [amt for dt, amt in entries if dt and dt > delivered]
            if posterior:
                schedule.amount_total_renewal_avg = sum(posterior) / len(posterior)
            else:
                schedule.amount_total_renewal_avg = 0.0

    _CONTACT_RATE_WINDOW_DAYS = 30

    @api.depends('line_ids.state', 'line_ids.outcome', 'line_ids.date_planned')
    def _compute_contact_rate_30d_display(self):
        """KPI 1 (Story 17-2 AC-1.3) — taux de contact 30 j par schedule.

        Formule : ``count(done) / count(done + overdue + unreachable_outcome)``
        sur les lignes des 30 derniers jours (fenêtre glissante ``date_planned``).
        Retourne '—' si aucune ligne éligible (dénominateur=0) — cf.
        MINEUR-5 readiness. Non aggregable en pivot (Char) — sert au tree
        KPI 2 et à la vue kanban/form du schedule.
        """
        today = fields.Date.today()
        window_start = fields.Date.subtract(today, days=self._CONTACT_RATE_WINDOW_DAYS)
        for schedule in self:
            recent = schedule.line_ids.filtered(
                lambda l: l.date_planned and l.date_planned >= window_start
            )
            eligible = recent.filtered(
                lambda l: l.state in ('done', 'overdue')
                or l.outcome == 'unreachable'
            )
            if not eligible:
                schedule.contact_rate_30d_display = '—'
                continue
            done_count = len(recent.filtered(lambda l: l.state == 'done'))
            rate = 100.0 * done_count / len(eligible)
            schedule.contact_rate_30d_display = "%.0f %%" % rate

    def _compute_email_open_rate_30d_display(self):
        """KPI 1 sous-métrique (Story 17-2 AC-1.4) — taux d'ouverture email 30 j.

        Odoo 18 CE sans ``mass_mailing`` ne track pas l'ouverture des mails
        transactionnels envoyés via ``mail.template`` (``notification_status``
        va jusqu'à ``sent`` / ``bounce`` / ``exception`` mais jamais
        ``opened``). D-KPI-EMAIL-TRACK : livrer la colonne avec fallback
        '—' systématique en V1, remonter en rétro epic 17 comme candidat V1.1.

        Volontairement AUCUNE dépendance ``@api.depends`` : le champ ne change
        pas tant qu'un tracking d'ouverture n'est pas branché. Retourne '—'
        pour tous les schedules.
        """
        for schedule in self:
            schedule.email_open_rate_30d_display = '—'

    # ==================================================================
    # Action smart button (Story 17-4 — AC4)
    # ==================================================================

    def action_open_lines(self):
        """Ouvre la vue list,form des lignes du calendrier courant.

        Story 17-4 — H6 : ``view_mode='list,form'`` (pas ``calendar`` — un
        schedule 13 étapes réparties sur 730 j n'a aucune valeur en vue
        month qui masquerait 22/24 mois).
        """
        self.ensure_one()
        return {
            'name': _("Étapes — %s", self.name),
            'type': 'ir.actions.act_window',
            'res_model': 'optical.followup.schedule.line',
            'view_mode': 'list,form',
            'domain': [('schedule_id', '=', self.id)],
            'context': {
                'default_schedule_id': self.id,
                'search_default_schedule_id': self.id,
            },
        }

    # ==================================================================
    # Cascade opt-out (livrée en 15.1)
    # ==================================================================

    def action_cancel_for_optout(self, reason=None):
        """Cascade opt-out : annule les calendriers actifs (``running``) ET
        suspendus (``paused``) de self, annule leurs lignes pendantes /
        en retard / suspendues, supprime les activités Odoo associées.
        Retourne ``(count_schedules, count_activities)``.

        Filtre interne ``state in ('running', 'paused')`` — les calendriers
        en pause SAV ne doivent pas ré-activer un dispositif sur un
        client désormais opt-out (FR-08 : verrouillage total). ``reason``
        non utilisé ici (l'origine du motif reste sur ``res.partner``),
        présent pour compatibilité de signature avec la story.
        """
        to_cancel = self.filtered(lambda s: s.state in ('running', 'paused'))
        if not to_cancel:
            return (0, 0)

        activities = self.env['mail.activity']
        for schedule in to_cancel:
            pending_lines = schedule.line_ids.filtered(
                lambda l: l.state in ('pending', 'overdue', 'paused')
            )
            activities |= pending_lines.mapped('activity_id')
            pending_lines.write({'state': 'cancelled'})

        count_activities = len(activities)
        if activities:
            activities.sudo().unlink()

        to_cancel.write({'state': 'cancelled'})
        return (len(to_cancel), count_activities)

    # ==================================================================
    # Suspension SAV et reprise (Story 16.2 — AC1, AC2, AC3, AC4, AC10)
    # ==================================================================

    def _pause_for_sav(self):
        """Met en pause les calendriers ``running`` pour motif SAV.

        Filtre self sur ``state == 'running'`` (idempotence — un schedule
        déjà paused n'est pas re-écrit, ce qui préserverait un
        ``sav_paused_date`` antérieur et éviterait un doublon de log).

        Effets par schedule :
          - lignes ``pending / overdue`` → ``paused``
          - activités ``mail.activity`` pointées → ``unlink``
          - schedule → ``paused`` + ``pause_reason='sav_open'`` + ``sav_paused_date=today``

        Le chatter partner est posté par le hook helpdesk (qui a le
        ``source_ticket`` sous la main pour un message contextualisé).

        Retourne le nombre de schedules effectivement mis en pause.
        """
        targets = self.filtered(lambda s: s.state == 'running')
        if not targets:
            return 0

        today = fields.Date.today()
        activities = self.env['mail.activity']
        for schedule in targets:
            pending_lines = schedule.line_ids.filtered(
                lambda l: l.state in ('pending', 'overdue')
            )
            activities |= pending_lines.mapped('activity_id')
            pending_lines.write({'state': 'paused'})

        if activities:
            activities.sudo().unlink()

        targets.write({
            'state': 'paused',
            'pause_reason': 'sav_open',
            'sav_paused_date': today,
        })
        return len(targets)

    def _resume_from_majority_pending(self):
        """Story 17-3 AC-A.3 — reprise des schedules ``paused / majority_pending``.

        Pattern parallèle à ``_resume_from_sav`` : lignes ``paused`` →
        ``pending`` (recalcul date : dépassées → today+1 j), schedule →
        ``running`` + ``pause_reason=False``.

        Garde-fou : NE réactive PAS les schedules paused pour un autre
        motif (SAV notamment — un SAV en cours doit rester paused).
        """
        targets = self.filtered(
            lambda s: s.state == 'paused' and s.pause_reason == 'majority_pending'
        )
        if not targets:
            return 0
        today = fields.Date.today()
        tomorrow = fields.Date.add(today, days=1)
        for schedule in targets:
            paused_lines = schedule.line_ids.filtered(
                lambda l: l.state == 'paused'
            )
            overdue_lines = paused_lines.filtered(
                lambda l: l.date_planned and l.date_planned < today
            )
            future_lines = paused_lines - overdue_lines
            if overdue_lines:
                overdue_lines.write({
                    'state': 'pending',
                    'date_planned': tomorrow,
                })
            if future_lines:
                future_lines.write({'state': 'pending'})
        targets.write({'state': 'running', 'pause_reason': False})
        return len(targets)

    def _pause_for_majority(self):
        """Story 17-3 AC-A.2 — pause ``running → paused / majority_pending``.

        Filtre self sur ``state == 'running'`` (idempotence — un schedule
        paused pour SAV n'est pas re-écrit).

        Effets par schedule :
          - lignes ``pending / overdue`` → ``paused``
          - activités ``mail.activity`` pointées → ``unlink``
          - schedule → ``paused`` + ``pause_reason='majority_pending'``
        """
        targets = self.filtered(lambda s: s.state == 'running')
        if not targets:
            return 0
        activities = self.env['mail.activity']
        for schedule in targets:
            pending_lines = schedule.line_ids.filtered(
                lambda l: l.state in ('pending', 'overdue')
            )
            activities |= pending_lines.mapped('activity_id')
            pending_lines.write({'state': 'paused'})
        if activities:
            activities.sudo().unlink()
        targets.write({
            'state': 'paused',
            'pause_reason': 'majority_pending',
        })
        return len(targets)

    def _resume_from_sav(self):
        """Reprend les calendriers ``paused / sav_open`` — cascade AC2 + AC3.

        Filtre self sur ``state == 'paused' AND pause_reason == 'sav_open'``
        (idempotence).

        Effets par schedule :
          - Lignes ``paused`` → ``pending`` + recalcul ``date_planned`` :
            - dépassées (``date_planned < today``) → ``today + 1 j``
            - à venir (``date_planned >= today``) → inchangé
          - schedule → ``running`` (``pause_reason`` et ``sav_paused_date``
            **conservés** pour audit — D-RESUME-DATE défaut)

        Le chatter partner est posté par le hook helpdesk (durée de pause
        calculée en amont depuis ``sav_paused_date``).

        Retourne le nombre de schedules effectivement repris.
        """
        targets = self.filtered(
            lambda s: s.state == 'paused' and s.pause_reason == 'sav_open'
        )
        if not targets:
            return 0

        today = fields.Date.today()
        tomorrow = fields.Date.add(today, days=1)

        for schedule in targets:
            paused_lines = schedule.line_ids.filtered(
                lambda l: l.state == 'paused'
            )
            # Regrouper les écritures pour limiter les writes SQL par ligne.
            overdue_lines = paused_lines.filtered(
                lambda l: l.date_planned and l.date_planned < today
            )
            future_lines = paused_lines - overdue_lines
            if overdue_lines:
                overdue_lines.write({
                    'state': 'pending',
                    'date_planned': tomorrow,
                })
            if future_lines:
                future_lines.write({'state': 'pending'})

        # Le write batch sur les schedules garde ``pause_reason`` et
        # ``sav_paused_date`` intacts (D-RESUME-DATE = conservation).
        targets.write({'state': 'running'})
        return len(targets)

    # ==================================================================
    # Injection d'étapes réservées par tier (Story 18-1 — AC-4)
    # ==================================================================

    def _inject_tier_steps(self, partner, delivered_date):
        """Story 18-1 AC-4.2 — injecte les étapes des plans réservés au tier.

        Généralise l'ancien ``_inject_vip_steps`` (couplé au XML ID
        ``plan_vip_extra``) : pour tout plan actif portant un ``tier_id`` tel
        que ``partner.optical_customer_tier_id.sequence >= plan.tier_id.
        sequence`` (sémantique cumulative — un tier supérieur reçoit aussi les
        attentions des tiers inférieurs), les étapes du plan sont matérialisées
        en supplément du plan principal.

        Contrat :
          - Retourne ``(n_created, n_skipped_birthday)`` :
              - ``n_created`` : nombre de lignes réservées effectivement créées
              - ``n_skipped_birthday`` : nombre d'étapes anniversaire skippées
                faute de ``partner.birthdate``
          - Aucune exception si le partner n'a pas de tier, si aucun plan
            réservé n'est éligible, ou si un plan est vide (garde-fou silencieux
            + log INFO)
          - Une étape ``birthday_step=True`` est skippée si ``partner.birthdate``
            manque ; les autres étapes du même plan restent créées (AC-4.3)

        Ne poste PAS de chatter — responsabilité de l'appelant
        (``_create_from_picking``), qui a le contexte complet pour un message
        unifié (pattern S17-4 double-post partner + schedule).
        """
        self.ensure_one()
        partner_tier = partner.optical_customer_tier_id
        if not partner_tier:
            return (0, 0)

        reserved_plans = self.env['optical.followup.plan'].sudo().search([
            ('active', '=', True),
            ('tier_id', '!=', False),
        ])
        eligible_plans = reserved_plans.filtered(
            lambda p: p.tier_id.sequence <= partner_tier.sequence
        )
        if not eligible_plans:
            _logger.info(
                "Injection tier skippée pour schedule %s : aucun plan réservé "
                "éligible au tier %s (partner %s).",
                self.id, partner_tier.name, partner.id,
            )
            return (0, 0)

        LineModel = self.env['optical.followup.schedule.line'].sudo()
        n_created = 0
        n_skipped_birthday = 0
        for plan in eligible_plans:
            for step in plan.step_ids:
                if step.birthday_step:
                    date_planned = _next_birthday_occurrence(
                        partner.birthdate, delivered_date,
                    )
                    if not date_planned:
                        _logger.info(
                            "Étape anniversaire skippée pour partner %s (%s) : "
                            "birthdate non renseignée.",
                            partner.id, partner.name,
                        )
                        n_skipped_birthday += 1
                        continue
                else:
                    date_planned = fields.Date.add(
                        delivered_date, days=step.offset_days,
                    )
                LineModel.create({
                    'schedule_id': self.id,
                    'step_id': step.id,
                    'sequence': step.sequence,
                    'date_planned': date_planned,
                    'date_planned_original': date_planned,
                    'state': 'pending',
                })
                n_created += 1
        return (n_created, n_skipped_birthday)

    @api.model
    def _sync_sav_state_for_partner(self, partner, source_ticket=None, reopened_ticket=None):
        """Pivot appelé par le hook ``helpdesk.ticket`` — synchronise l'état
        SAV de TOUS les schedules ``running / paused`` d'un partner.

        4 cas selon (état tickets ouverts) × (état schedules) :
          1. Tickets ouverts + schedule ``running``  → pause + chatter ouverture
          2. Tickets ouverts + schedule ``paused`` SAV + ``reopened_ticket``
             renseigné → chatter réouverture uniquement (pas de re-write,
             préserve ``sav_paused_date``)
          3. Aucun ticket ouvert + schedule ``paused`` SAV → reprise + chatter
          4. Autre → no-op silencieux

        ``source_ticket`` (optionnel) permet de nommer le ticket dans le
        chatter d'ouverture (cas 1).

        ``reopened_ticket`` (optionnel) : ticket dont la transition
        closed=True→False a été détectée par le hook write. **Seul cas
        où le chatter « rouvert » est posté** — évite le faux positif sur
        création d'un 2ᵉ ticket ou write neutre de ``stage_id`` (AC10).

        Le contexte ``optical_followup_skip_chatter=True`` mute les chatters
        SAV — utilisé par ``_create_from_picking`` (D-CROSS-SAV-CHATTER)
        qui poste son propre message unifié « Réachat pendant SAV… ».

        Résilience : chaque schedule est traité dans un savepoint pour
        qu'une exception isolée ne casse pas le batch (AC2 rétro 15). Le
        chatter est posté HORS savepoint — un échec de ``message_post``
        (rare mais possible) ne doit pas rollback la pause/reprise.
        """
        if not partner:
            return
        skip_chatter = self.env.context.get('optical_followup_skip_chatter', False)

        open_tickets = self.env['helpdesk.ticket'].sudo().search([
            ('partner_id', '=', partner.id),
            ('closed', '=', False),
        ])
        schedules = self.sudo().search([
            ('partner_id', '=', partner.id),
            ('state', 'in', ('running', 'paused')),
        ])
        if not schedules:
            return

        ticket_name = source_ticket.name if source_ticket and source_ticket.name else _("(sans référence)")

        if open_tickets:
            running = schedules.filtered(lambda s: s.state == 'running')
            already_paused_sav = schedules.filtered(
                lambda s: s.state == 'paused' and s.pause_reason == 'sav_open'
            )
            for schedule in running:
                try:
                    with self.env.cr.savepoint():
                        schedule._pause_for_sav()
                except Exception as exc:  # noqa: BLE001 — résilience hook
                    _logger.exception(
                        "Sync SAV — pause schedule %s ignorée (%s).",
                        schedule.id, exc,
                    )
                    continue
                if skip_chatter:
                    continue
                try:
                    partner.sudo().message_post(body=_(
                        "Calendrier de fidélisation suspendu automatiquement : "
                        "ticket SAV %(ticket)s ouvert.",
                        ticket=ticket_name,
                    ))
                    # Story 17-4 AC6 — double-post schedule HORS savepoint,
                    # body IDENTIQUE (M11), subtype mt_note (L12 : pas de
                    # notification email).
                    schedule.sudo().message_post(
                        body=_(
                            "Calendrier de fidélisation suspendu automatiquement : "
                            "ticket SAV %(ticket)s ouvert.",
                            ticket=ticket_name,
                        ),
                        subtype_xmlid='mail.mt_note',
                    )
                except Exception as exc:  # noqa: BLE001 — chatter non critique
                    _logger.exception(
                        "Sync SAV — chatter pause partner %s ignoré (%s).",
                        partner.id, exc,
                    )
            # Cas 2 : ré-ouverture EXPLICITE d'un ticket clos (transition
            # closed=True→False détectée par le hook write). Pas de chatter
            # sur simple création d'un nouveau ticket ni sur write neutre
            # de stage_id — la présence de ``reopened_ticket`` est la
            # condition sine qua non (H1/H2/H3 code review).
            if already_paused_sav and reopened_ticket and not skip_chatter:
                reopened_name = reopened_ticket.name or _("(sans référence)")
                try:
                    partner.sudo().message_post(body=_(
                        "Ticket SAV %(ticket)s rouvert — calendrier maintenu en suspension.",
                        ticket=reopened_name,
                    ))
                    # Story 17-4 AC6 (M7 revue) — double-post sur chaque
                    # schedule concerné pour éviter le trou temporel dans
                    # le chatter du schedule (« suspendu » puis rien puis
                    # « repris »). Body IDENTIQUE (M11), subtype mt_note.
                    for schedule in already_paused_sav:
                        schedule.sudo().message_post(
                            body=_(
                                "Ticket SAV %(ticket)s rouvert — calendrier "
                                "maintenu en suspension.",
                                ticket=reopened_name,
                            ),
                            subtype_xmlid='mail.mt_note',
                        )
                except Exception as exc:  # noqa: BLE001 — chatter non critique
                    _logger.exception(
                        "Sync SAV — chatter réouverture partner %s ignoré (%s).",
                        partner.id, exc,
                    )
        else:
            # Aucun ticket ouvert : reprendre les schedules paused SAV.
            to_resume = schedules.filtered(
                lambda s: s.state == 'paused' and s.pause_reason == 'sav_open'
            )
            for schedule in to_resume:
                paused_date = schedule.sav_paused_date
                try:
                    with self.env.cr.savepoint():
                        schedule._resume_from_sav()
                except Exception as exc:  # noqa: BLE001 — résilience hook
                    _logger.exception(
                        "Sync SAV — reprise schedule %s ignorée (%s).",
                        schedule.id, exc,
                    )
                    continue
                if skip_chatter:
                    continue
                try:
                    duration = (
                        (fields.Date.today() - paused_date).days
                        if paused_date else 0
                    )
                    partner.sudo().message_post(body=_(
                        "Calendrier de fidélisation repris automatiquement : "
                        "tous les tickets SAV sont clos (durée de pause : %(n)s jour(s)).",
                        n=duration,
                    ))
                    # Story 17-4 AC6 — double-post schedule HORS savepoint,
                    # body IDENTIQUE (M11), subtype mt_note (L12).
                    schedule.sudo().message_post(
                        body=_(
                            "Calendrier de fidélisation repris automatiquement : "
                            "tous les tickets SAV sont clos (durée de pause : %(n)s jour(s)).",
                            n=duration,
                        ),
                        subtype_xmlid='mail.mt_note',
                    )
                except Exception as exc:  # noqa: BLE001 — chatter non critique
                    _logger.exception(
                        "Sync SAV — chatter reprise partner %s ignoré (%s).",
                        partner.id, exc,
                    )

    # ==================================================================
    # Création d'un calendrier depuis un picking outgoing (AC1)
    # ==================================================================

    @api.model
    def _create_from_picking(self, picking):
        """Orchestre la création d'un calendrier depuis un picking validé.

        Étapes :
          1. Vérifier partner éligible (helper 15.1 ``_can_start_followup``).
          2. Fermer d'éventuels calendriers ``running`` antérieurs (réachat AC8).
          3. Sélectionner le preset applicable via ``_select_for_sale_order``.
          4. Créer le schedule + lignes ``pending`` + poster chatter SO.
        """
        picking.ensure_one()
        sale_order = picking.sale_id
        if not sale_order:
            return self.browse()

        partner = sale_order.partner_id
        eligible, reason = partner._can_start_followup()
        if not eligible:
            _logger.info(
                "Calendrier followup non créé pour SO %s : motif %s.",
                sale_order.name, reason,
            )
            return self.browse()

        plan = self.env['optical.followup.plan']._select_for_sale_order(sale_order)
        if not plan:
            _logger.warning(
                "Aucun preset applicable trouvé pour SO %s.",
                sale_order.name,
            )
            return self.browse()

        # Réachat anticipé : fermer les running/paused existants POUR CE
        # PARTNER ET CETTE BOUTIQUE (AC5 / D-SCOPE). Le scope warehouse
        # évite qu'un achat à VDN clôture un calendrier actif à Corniche
        # pour le même client (chaîne multi-boutique — cf. code review
        # S15.2 M1). Story 16.2 étend au state=paused pour couvrir le
        # cas croisé « réachat pendant SAV en cours » (AC6).
        warehouse = picking.picking_type_id.warehouse_id
        old_schedules = self.sudo().search([
            ('partner_id', '=', partner.id),
            ('warehouse_id', '=', warehouse.id),
            ('state', 'in', ('running', 'paused')),
        ])
        n_cancelled_old = 0
        had_paused_sav = False
        if old_schedules:
            had_paused_sav = any(
                s.state == 'paused' and s.pause_reason == 'sav_open'
                for s in old_schedules
            )
            for old in old_schedules:
                # Story 16.2 AC6 : inclure les lignes 'paused' déjà mises
                # de côté par une pause SAV — sinon elles resteraient
                # orphelines sur un schedule fulfilled.
                pending = old.line_ids.filtered(
                    lambda l: l.state in ('pending', 'overdue', 'paused')
                )
                acts = pending.mapped('activity_id')
                pending.write({
                    'state': 'cancelled',
                    'outcome_note': _("Réachat anticipé — nouveau calendrier ouvert."),
                })
                if acts:
                    acts.sudo().unlink()
                n_cancelled_old += len(pending)
            old_schedules.write({'state': 'fulfilled'})

        delivered_date = fields.Date.to_date(picking.date_done) or fields.Date.context_today(self)

        referent = partner._get_followup_referent(sale_order=sale_order)

        schedule = self.sudo().create({
            'name': self.env['ir.sequence'].next_by_code(
                'optical.followup.schedule'
            ) or (_("SUIVI/%s") % (sale_order.name or 'NEW')),
            'partner_id': partner.id,
            'warehouse_id': warehouse.id,
            'sale_order_id': sale_order.id,
            'picking_id': picking.id,
            'plan_id': plan.id,
            'referent_user_id': referent.id if referent else False,
            'delivered_date': delivered_date,
            'state': 'running',
        })

        LineModel = self.env['optical.followup.schedule.line'].sudo()
        for step in plan.step_ids:
            LineModel.create({
                'schedule_id': schedule.id,
                'step_id': step.id,
                'sequence': step.sequence,
                'date_planned': fields.Date.add(delivered_date, days=step.offset_days),
                'date_planned_original': fields.Date.add(delivered_date, days=step.offset_days),
                'state': 'pending',
            })

        sale_order.sudo().write({
            'followup_schedule_id': schedule.id,
            'delivered_date': delivered_date,
        })

        # Story 18-1 AC-4 — injection des étapes réservées au tier APRÈS les
        # lignes du plan principal (le compteur d'étapes du chatter principal
        # reste len(plan.step_ids) pour éviter de « mentir » sur le preset lu ;
        # les étapes réservées sont additionnelles, tracées séparément).
        n_vip_created, n_vip_skipped = schedule._inject_tier_steps(
            partner, delivered_date,
        )

        sale_order.message_post(body=_(
            "Calendrier de fidélisation démarré : %(plan)s (%(n)s étapes).",
            plan=plan.name,
            n=len(plan.step_ids),
        ))
        # Story 17-4 AC6 — double-post schedule (démarrage). Body IDENTIQUE
        # à sale_order.message_post ci-dessus (M11), subtype mt_note (L12).
        # Try/except : chatter non critique, ne doit pas bloquer la création.
        try:
            schedule.message_post(
                body=_(
                    "Calendrier de fidélisation démarré : %(plan)s (%(n)s étapes).",
                    plan=plan.name,
                    n=len(plan.step_ids),
                ),
                subtype_xmlid='mail.mt_note',
            )
        except Exception as exc:  # noqa: BLE001
            _logger.exception(
                "Chatter création schedule %s ignoré (%s).", schedule.id, exc,
            )

        # Story 18-1 AC-4.3 — chatter dédié pour les étapes réservées ajoutées
        # (partner + schedule, subtype mt_note, POSTÉ APRÈS le message
        # principal de démarrage). Libellé paramétré par le NOM du tier (plus
        # de « VIP » en dur). Si anniversaire skippé faute de birthdate, le
        # message le mentionne. Si aucune étape réservée n'a été créée
        # (partner sans tier réservé, plan inactif), silence.
        if n_vip_created > 0:
            tier_name = partner.optical_customer_tier_id.name or _("(tier)")
            if partner.optical_customer_tier_override_id:
                reason_body = _("override manuel")
            else:
                reason_body = _("seuil CA atteint")
            skip_note = ""
            if n_vip_skipped:
                skip_note = _(
                    " — anniversaire skippé (date de naissance manquante)"
                )
            body_vip = _(
                "%(n)s étape(s) réservée(s) au tier « %(tier)s » ajoutée(s) "
                "au calendrier (%(reason)s)%(skip)s.",
                n=n_vip_created,
                tier=tier_name,
                reason=reason_body,
                skip=skip_note,
            )
            try:
                partner.sudo().message_post(
                    body=body_vip,
                    subtype_xmlid='mail.mt_note',
                )
                schedule.sudo().message_post(
                    body=body_vip,
                    subtype_xmlid='mail.mt_note',
                )
            except Exception as exc:  # noqa: BLE001 — chatter non critique
                _logger.exception(
                    "Chatter injection tier schedule %s ignoré (%s).",
                    schedule.id, exc,
                )

        if old_schedules:
            if had_paused_sav:
                # Story 16.2 D-CROSS-SAV-CHATTER : chatter unifié quand le
                # réachat intervient sur un calendrier en pause SAV — évite
                # le ping-pong « ancien clôturé » + « nouveau créé » +
                # « nouveau immédiatement paused ».
                partner.message_post(body=_(
                    "Réachat anticipé pendant SAV en cours : ancien calendrier "
                    "clôturé (%(n)s étapes annulées), nouveau calendrier %(name)s "
                    "ouvert (immédiatement suspendu — ticket(s) SAV toujours ouvert(s)).",
                    n=n_cancelled_old,
                    name=schedule.name,
                ))
                # Story 17-4 AC6 — double-post sur le nouveau schedule
                # (l'ancien est fulfilled, chatter figé). Body IDENTIQUE (M11).
                try:
                    schedule.message_post(
                        body=_(
                            "Réachat anticipé pendant SAV en cours : ancien calendrier "
                            "clôturé (%(n)s étapes annulées), nouveau calendrier %(name)s "
                            "ouvert (immédiatement suspendu — ticket(s) SAV toujours ouvert(s)).",
                            n=n_cancelled_old,
                            name=schedule.name,
                        ),
                        subtype_xmlid='mail.mt_note',
                    )
                except Exception as exc:  # noqa: BLE001
                    _logger.exception(
                        "Chatter réachat pendant SAV schedule %s ignoré (%s).",
                        schedule.id, exc,
                    )
            else:
                partner.message_post(body=_(
                    "Réachat anticipé : ancien calendrier clôturé (%(n)s étapes annulées), "
                    "nouveau calendrier %(name)s ouvert.",
                    n=n_cancelled_old,
                    name=schedule.name,
                ))
                # Story 17-4 AC6 — double-post sur le nouveau schedule.
                # Body IDENTIQUE au partner.message_post ci-dessus (M11).
                try:
                    schedule.message_post(
                        body=_(
                            "Réachat anticipé : ancien calendrier clôturé (%(n)s étapes annulées), "
                            "nouveau calendrier %(name)s ouvert.",
                            n=n_cancelled_old,
                            name=schedule.name,
                        ),
                        subtype_xmlid='mail.mt_note',
                    )
                except Exception as exc:  # noqa: BLE001
                    _logger.exception(
                        "Chatter réachat schedule %s ignoré (%s).",
                        schedule.id, exc,
                    )

        # Story 16.2 AC6 : si des tickets SAV sont ouverts pour ce partner,
        # basculer immédiatement le nouveau schedule en pause. Le context
        # skip_chatter=True n'est activé que si le chatter unifié
        # « pendant SAV » a déjà été posté ci-dessus ; sinon on laisse
        # ``_sync_sav_state_for_partner`` poster son propre message de pause
        # (edge : partner avec ticket ouvert préexistant mais pas de
        # calendrier antérieur).
        sync_ctx = (
            {'optical_followup_skip_chatter': True}
            if had_paused_sav else {}
        )
        self.with_context(**sync_ctx)._sync_sav_state_for_partner(partner)

        return schedule

    # ==================================================================
    # Cron quotidien (AC3, AC4, AC7)
    # ==================================================================

    @api.model
    def _run_daily_cron(self):
        """Entry-point du cron quotidien 00h30.

        Trois passes :
          1. Matérialisation des ``mail.activity`` pour les lignes ``pending``
             dont ``date_planned = today + 3j`` (AC3).
          2. Marquage ``overdue`` des lignes ``pending`` dont
             ``date_planned < today`` (AC4).
          3. Alerte picking en attente > 7 jours (AC7).

        Chaque ligne est isolée dans un savepoint : une exception sur une
        ligne n'empêche pas les autres d'être traitées (résilience prod —
        cf. code review S15.2).
        """
        today = fields.Date.today()
        target = fields.Date.add(today, days=3)

        # (1) Matérialisation J-3
        lines_to_materialize = self.env['optical.followup.schedule.line'].sudo().search([
            ('state', '=', 'pending'),
            ('date_planned', '=', target),
            ('schedule_id.state', '=', 'running'),
            ('activity_id', '=', False),
        ])
        for line in lines_to_materialize:
            try:
                with self.env.cr.savepoint():
                    line._materialize_step_activity()
            except Exception as exc:  # noqa: BLE001 — résilience cron
                _logger.exception(
                    "Cron matérialisation : ligne %s ignorée (%s).",
                    line.id, exc,
                )

        # (2) Marquage overdue
        overdue_lines = self.env['optical.followup.schedule.line'].sudo().search([
            ('state', '=', 'pending'),
            ('date_planned', '<', today),
            ('schedule_id.state', '=', 'running'),
        ])
        if overdue_lines:
            overdue_lines.write({'state': 'overdue'})

        # (3) Alerte picking en attente > 7 j
        self._check_late_pickings()

    # Fenêtre d'analyse pour la passe "fermeture d'alertes picking > 7 j".
    # Au-delà, la SO est jugée trop ancienne pour qu'une réouverture de
    # picking soit crédible — on l'exclut du scan pour maîtriser le coût
    # du cron dans le temps (cf. code review S15.2 M4).
    _LATE_ALERT_CLOSURE_WINDOW_DAYS = 180

    @api.model
    def _check_late_pickings(self):
        """Passe alerte picking > 7 j (mitigation R1 archi § 4.10).

        Crée une mail.activity de type warning sur la SO pour le manager
        boutique. Idempotence via ``sale.order.picking_late_alert_sent``.
        Fermeture automatique quand tous les pickings passent ``done``
        (via pointeur ``picking_late_alert_activity_id`` — pas de match
        fragile sur summary traduit).
        """
        today = fields.Date.today()
        cutoff = fields.Date.subtract(today, days=7)
        SO = self.env['sale.order'].sudo()

        # SO à alerter : date_order <= cutoff, state in sale/done, alert non envoyée,
        # picking outgoing encore ouvert (assigned/waiting/confirmed).
        candidates = SO.search([
            ('state', 'in', ('sale', 'done')),
            ('picking_late_alert_sent', '=', False),
            ('date_order', '<=', cutoff),
        ])
        warning_type = self.env.ref(
            'mail.mail_activity_data_warning', raise_if_not_found=False,
        )
        if not warning_type:
            _logger.warning(
                "Alerte picking > 7 j : type 'mail.mail_activity_data_warning' "
                "introuvable — fallback sur 'mail_activity_data_todo'."
            )
            warning_type = self.env.ref(
                'mail.mail_activity_data_todo', raise_if_not_found=False,
            )
        so_model = self.env['ir.model']._get('sale.order')

        for so in candidates:
            try:
                with self.env.cr.savepoint():
                    self._alert_late_picking_one(so, warning_type, so_model, today)
            except Exception as exc:  # noqa: BLE001 — résilience cron
                _logger.exception(
                    "Alerte picking > 7 j SO %s ignorée (%s).", so.name, exc,
                )

        # Fermeture automatique — bornée à une fenêtre glissante pour éviter
        # de scanner l'historique complet à chaque exécution.
        closure_horizon = fields.Datetime.subtract(
            fields.Datetime.now(), days=self._LATE_ALERT_CLOSURE_WINDOW_DAYS,
        )
        closable = SO.search([
            ('picking_late_alert_sent', '=', True),
            ('picking_late_alert_activity_id', '!=', False),
            ('date_order', '>=', closure_horizon),
        ])
        for so in closable:
            try:
                with self.env.cr.savepoint():
                    self._close_late_picking_alert_if_done(so)
            except Exception as exc:  # noqa: BLE001 — résilience cron
                _logger.exception(
                    "Fermeture alerte picking SO %s ignorée (%s).", so.name, exc,
                )

    @api.model
    def _alert_late_picking_one(self, so, warning_type, so_model, today):
        """Crée l'activité warning pour une SO donnée (isolée du batch)."""
        open_pickings = so.picking_ids.filtered(
            lambda p: p.picking_type_id.code == 'outgoing'
            and p.state in ('assigned', 'waiting', 'confirmed')
        )
        if not open_pickings:
            return
        manager_user = self._resolve_late_alert_manager(so)
        if not manager_user:
            _logger.info(
                "Alerte picking > 7 j SO %s : aucun manager résolu — skip.",
                so.name,
            )
            return
        activity = self.env['mail.activity'].sudo().create({
            'res_model': 'sale.order',
            'res_model_id': so_model.id,
            'res_id': so.id,
            'activity_type_id': warning_type.id,
            'user_id': manager_user.id,
            'summary': _("Picking en attente > 7 j — remise non validée"),
            'note': plaintext2html(_(
                "Picking en attente > 7 j — remise non validée. "
                "Vérifier situation client."
            )),
            'date_deadline': today,
        })
        so.write({
            'picking_late_alert_sent': True,
            'picking_late_alert_activity_id': activity.id,
        })

    @api.model
    def _close_late_picking_alert_if_done(self, so):
        """Ferme l'activité warning si tous les pickings outgoing sont ``done``.

        S'appuie sur ``picking_late_alert_activity_id`` (pointeur direct)
        au lieu d'un match sur ``summary`` traduit — insensible à la langue
        de l'utilisateur cron entre deux passes.
        """
        still_open = so.picking_ids.filtered(
            lambda p: p.picking_type_id.code == 'outgoing'
            and p.state in ('assigned', 'waiting', 'confirmed')
        )
        if still_open:
            return
        activity = so.picking_late_alert_activity_id
        if activity:
            activity.sudo().unlink()
            so.message_post(body=_(
                "Alerte 'Picking en attente > 7 j' fermée automatiquement — "
                "pickings outgoing tous validés."
            ))
        # Le pointeur est nettoyé par ondelete='set null' de l'activité.
        # Le flag ``picking_late_alert_sent`` reste True (historique).

    @api.model
    def _resolve_late_alert_manager(self, sale_order):
        """Heuristique de résolution du manager boutique pour l'alerte R1.

        Priorité :
          1. sale_order.warehouse_id.company_id.chatter_manager_user_id
             (si le champ existe — sinon skip)
          2. sale_order.user_id (commercial de la SO)
          3. Premier user du group_optical_manager scopé à la boutique.
        """
        warehouse = sale_order.warehouse_id
        company = warehouse.company_id
        if 'chatter_manager_user_id' in company._fields and company.chatter_manager_user_id:
            return company.chatter_manager_user_id
        if sale_order.user_id:
            return sale_order.user_id
        group = self.env.ref('optical.group_optical_manager', raise_if_not_found=False)
        if group:
            for user in group.users:
                # Scoper à la boutique via optical_warehouse_ids si renseigné
                if 'optical_warehouse_ids' in user._fields:
                    if not user.optical_warehouse_ids or warehouse in user.optical_warehouse_ids:
                        return user
                else:
                    return user
        return self.env['res.users']

    # ==================================================================
    # Digest mail overdue (AC9)
    # ==================================================================

    @api.model
    def _run_digest_overdue(self):
        """Cron 07h00 : envoie un digest mail par référent avec ses lignes overdue."""
        Line = self.env['optical.followup.schedule.line'].sudo()
        overdue_lines = Line.search([
            ('state', '=', 'overdue'),
            ('schedule_id.state', '=', 'running'),
        ])
        if not overdue_lines:
            return

        template = self.env.ref(
            'optical_crm_followup.email_digest_overdue',
            raise_if_not_found=False,
        )
        if not template:
            _logger.warning("Digest overdue : template mail introuvable — skip.")
            return

        by_user = {}
        for line in overdue_lines:
            referent = line.schedule_id.referent_user_id
            if not referent:
                continue
            by_user.setdefault(referent.id, self.env['optical.followup.schedule.line'])
            by_user[referent.id] |= line

        for user_id, lines in by_user.items():
            user = self.env['res.users'].browse(user_id)
            if not user.partner_id.email:
                _logger.info(
                    "Digest overdue : user %s sans email — skip.", user.login,
                )
                continue
            # On envoie 1 mail par user en passant le premier record + context
            # avec la liste complète (le template peut boucler).
            template.with_context(
                overdue_line_ids=lines.ids,
                overdue_count=len(lines),
            ).send_mail(
                lines[0].id, force_send=True, email_values={
                    'email_to': user.partner_id.email,
                },
            )


    # ==================================================================
    # Story 17-3 AC-A + AC-E — Cron RH quotidien 06 h 00 fusionnée
    # ==================================================================

    @api.model
    def _run_daily_rh_cron(self):
        """Entry-point du cron RH quotidien 06 h 00.

        Passes ordonnées idempotentes (chaque passe isolée en savepoint) :
          1. Bascule leaves ``planned → active`` (date_start <= today)
          2. Bascule leaves ``active → ended`` (date_end < today)
          3. Envoi mail renouvellement consentement à J+18 ans (AC-A.1)
          4. Pause auto schedules ``majority_pending`` à J+90 j (AC-A.2)

        Cohérent avec ``_run_daily_cron`` (3 passes fusionnées matérialisation
        + overdue + alerte picking) — convention S15.2 (D-COMPLIANCE-LEAVE-BULK-MERGE = A).
        """
        today = fields.Date.today()
        Leave = self.env['optical.followup.user.leave'].sudo()

        # (1) Bascule leaves planned → active
        to_activate = Leave.search([
            ('state', '=', 'planned'),
            ('date_start', '<=', today),
        ])
        for leave in to_activate:
            try:
                with self.env.cr.savepoint():
                    leave._activate_and_reassign()
            except Exception as exc:  # noqa: BLE001 — résilience
                _logger.exception(
                    "Cron RH — activation leave %s ignorée (%s).",
                    leave.id, exc,
                )

        # (2) Bascule leaves active → ended
        to_end = Leave.search([
            ('state', '=', 'active'),
            ('date_end', '<', today),
        ])
        for leave in to_end:
            try:
                with self.env.cr.savepoint():
                    leave._end_and_revert()
            except Exception as exc:  # noqa: BLE001 — résilience
                _logger.exception(
                    "Cron RH — fin leave %s ignorée (%s).", leave.id, exc,
                )

        # (3) Envoi mail renouvellement consentement à J+18 ans
        self._process_majority_transitions()

    _MAJORITY_GRACE_DAYS = 90

    @api.model
    def _process_majority_transitions(self):
        """Story 17-3 AC-A.1 + AC-A.2 — traitement quotidien des transitions.

        Deux sous-passes :
          A. Partners ``optical_followup_consent_by_legal_rep=True`` +
             ``birthdate + 18 ans <= today`` + majority_request_date=False →
             envoi mail + pose ``majority_request_date=today`` + chatter.
          B. Partners avec ``majority_request_date + 90 j <= today`` +
             schedule ``running`` → passage ``paused / majority_pending`` +
             activité warning manager + chatter.

        Résilience : chaque partner isolé en savepoint.
        """
        today = fields.Date.today()
        Partner = self.env['res.partner'].sudo()

        # (A) Transition majorité — mail J+18 ans
        eighteen_years_ago = fields.Date.subtract(today, years=18)
        candidates_majority = Partner.search([
            ('optical_followup_consent_by_legal_rep', '=', True),
            ('birthdate', '!=', False),
            ('birthdate', '<=', eighteen_years_ago),
            ('optical_followup_majority_request_date', '=', False),
            ('optical_anonymized', '=', False),
        ])
        template = self.env.ref(
            'optical_crm_followup.email_majority_renew_consent',
            raise_if_not_found=False,
        )
        for partner in candidates_majority:
            try:
                with self.env.cr.savepoint():
                    self._process_majority_send_mail(partner, template, today)
            except Exception as exc:  # noqa: BLE001 — résilience
                _logger.exception(
                    "Cron RH — transition majorité partner %s ignorée (%s).",
                    partner.id, exc,
                )

        # (B) Pause auto à J+90 j sans confirmation
        threshold_pause = fields.Date.subtract(today, days=self._MAJORITY_GRACE_DAYS)
        candidates_pause = Partner.search([
            ('optical_followup_consent_by_legal_rep', '=', True),
            ('optical_followup_majority_request_date', '!=', False),
            ('optical_followup_majority_request_date', '<=', threshold_pause),
            ('optical_anonymized', '=', False),
        ])
        for partner in candidates_pause:
            try:
                with self.env.cr.savepoint():
                    self._process_majority_pause(partner)
            except Exception as exc:  # noqa: BLE001 — résilience
                _logger.exception(
                    "Cron RH — pause majorité partner %s ignorée (%s).",
                    partner.id, exc,
                )

    @api.model
    def _process_majority_send_mail(self, partner, template, today):
        """AC-A.1 — envoie le mail + pose date + chatter.

        Sans email : log warning + activité warning manager, pas d'exception.
        """
        running_schedules = self.sudo().search([
            ('partner_id', '=', partner.id),
            ('state', '=', 'running'),
        ])
        if not running_schedules:
            return  # partner sans schedule actif : rien à déclencher
        if not partner.email:
            _logger.warning(
                "Transition majorité partner %s : aucun email — activité "
                "warning manager créée.", partner.id,
            )
            # Créer activité warning sur last SO
            last_so = self.env['sale.order'].sudo().search([
                ('partner_id', '=', partner.id),
            ], order='date_order desc', limit=1)
            if last_so:
                manager = self._resolve_late_alert_manager(last_so)
                if manager:
                    warning_type = self.env.ref(
                        'mail.mail_activity_data_warning',
                        raise_if_not_found=False,
                    )
                    if warning_type:
                        so_model = self.env['ir.model']._get('sale.order')
                        self.env['mail.activity'].sudo().create({
                            'res_model': 'sale.order',
                            'res_model_id': so_model.id,
                            'res_id': last_so.id,
                            'activity_type_id': warning_type.id,
                            'user_id': manager.id,
                            'summary': _(
                                "Renouvellement consentement — client majeur sans email"
                            ),
                            'date_deadline': today,
                        })
            return
        if template:
            try:
                template.sudo().send_mail(
                    partner.id,
                    force_send=True,
                    email_values={'email_to': partner.email},
                )
            except Exception as exc:  # noqa: BLE001 — résilience mail
                _logger.exception(
                    "Envoi mail majorité partner %s ignoré (%s).",
                    partner.id, exc,
                )
        partner.with_context(optical_anonymize_in_progress=False).sudo().write({
            'optical_followup_majority_request_date': today,
        })
        body = _(
            "Renouvellement de consentement personnel demandé — email "
            "envoyé à %(email)s. Sans réponse sous %(days)s j, le "
            "calendrier sera mis en pause.",
            email=partner.email,
            days=self._MAJORITY_GRACE_DAYS,
        )
        try:
            partner.sudo().message_post(body=body)
            for schedule in running_schedules:
                schedule.sudo().message_post(
                    body=body, subtype_xmlid='mail.mt_note',
                )
        except Exception as exc:  # noqa: BLE001 — chatter non critique
            _logger.exception(
                "Chatter majorité partner %s ignoré (%s).", partner.id, exc,
            )

    @api.model
    def _process_majority_pause(self, partner):
        """AC-A.2 — pause auto à J+90 sans confirmation.

        Idempotence : les schedules déjà paused (SAV notamment) ne sont pas
        re-écrits — le pivot ``_pause_for_majority`` filtre sur running only.
        """
        schedules = self.sudo().search([
            ('partner_id', '=', partner.id),
            ('state', '=', 'running'),
        ])
        n = schedules._pause_for_majority()
        if not n:
            return  # pas de running → rien à faire (idempotence)
        # Activité warning manager
        last_so = self.env['sale.order'].sudo().search([
            ('partner_id', '=', partner.id),
        ], order='date_order desc', limit=1)
        if last_so:
            manager = self._resolve_late_alert_manager(last_so)
            if manager:
                warning_type = self.env.ref(
                    'mail.mail_activity_data_warning',
                    raise_if_not_found=False,
                )
                if warning_type:
                    so_model = self.env['ir.model']._get('sale.order')
                    self.env['mail.activity'].sudo().create({
                        'res_model': 'sale.order',
                        'res_model_id': so_model.id,
                        'res_id': last_so.id,
                        'activity_type_id': warning_type.id,
                        'user_id': manager.id,
                        'summary': _(
                            "Consentement à confirmer — client majeur, aucune "
                            "confirmation reçue sous 90 j."
                        ),
                        'date_deadline': fields.Date.today(),
                    })
        body = _(
            "Calendrier de fidélisation suspendu automatiquement : "
            "consentement à confirmer (client devenu majeur depuis %(days)s j).",
            days=self._MAJORITY_GRACE_DAYS,
        )
        try:
            partner.sudo().message_post(body=body)
            for schedule in schedules:
                schedule.sudo().message_post(
                    body=body, subtype_xmlid='mail.mt_note',
                )
        except Exception as exc:  # noqa: BLE001 — chatter non critique
            _logger.exception(
                "Chatter pause majorité partner %s ignoré (%s).",
                partner.id, exc,
            )

    # ==================================================================
    # Story 17-3 AC-C — Continuité départ commercial
    # ==================================================================

    @api.model
    def _resolve_reassignment_target(self, partner, old_user):
        """Heuristique explicite de résolution du nouveau référent.

        Story 17-3 AC-C.1 — 4 niveaux dans l'ordre documenté :

          1. Dernier ``sale.order.user_id`` du partner (SO state in
             ('sale', 'done'), date_order desc) si actif ET ≠ old_user ET ≠ False
          2. ``warehouse_id.manager_id`` de la dernière SO (si existant + actif)
          3. Premier user actif de ``group_optical_manager`` scopé à cette
             warehouse (via ``optical_warehouse_ids``)
          4. Sinon retour ``res.users()`` vide → activité orpheline (unlink
             + chatter partner « faute de repreneur identifiable »).

        Retourne un ``res.users`` recordset (vide si aucun héritier).
        """
        SO = self.env['sale.order'].sudo()
        last_so = SO.search([
            ('partner_id', '=', partner.id),
            ('state', 'in', ('sale', 'done')),
        ], order='date_order desc', limit=1)

        # (1) Dernier commercial de SO
        if last_so and last_so.user_id and last_so.user_id.active and last_so.user_id != old_user:
            return last_so.user_id

        # (2) warehouse_id.manager_id de la dernière SO (via team_id.user_id ou stock manager)
        if last_so and last_so.warehouse_id:
            manager_field_names = ('manager_id', 'user_id')
            for field_name in manager_field_names:
                if field_name in last_so.warehouse_id._fields:
                    candidate = last_so.warehouse_id[field_name]
                    if candidate and candidate.active and candidate != old_user:
                        return candidate

        # (3) Premier manager scopé à la warehouse — tri déterministe par login
        # pour garantir la même résolution sur toutes les instances (audit).
        group = self.env.ref('optical.group_optical_manager', raise_if_not_found=False)
        if group and last_so and last_so.warehouse_id:
            warehouse = last_so.warehouse_id
            for user in group.users.sorted('login'):
                if not user.active or user == old_user:
                    continue
                if 'optical_warehouse_ids' in user._fields:
                    if not user.optical_warehouse_ids or warehouse in user.optical_warehouse_ids:
                        return user
                else:
                    return user

        return self.env['res.users']

    @api.model
    def _sync_referent_change_for_user(self, user, snapshot):
        """Story 17-3 AC-C — pivot appelé post-désactivation d'un user.

        ``snapshot`` est le dict issu du hook ``res.users.write`` (capture
        AVANT super) :
          ``{'partner_ids': [...], 'activity_ids': [...], 'schedule_ids': [...]}``

        Pour chaque activité : résolution nouveau référent + reassignation
        (ou unlink si orpheline). Pour chaque schedule paused (SAV ou
        majority) : réassignation de ``referent_user_id``. Chatter partner
        dédupliqué (un partner concerné par 3 activités reçoit 1 message).

        Résilience : chaque partner isolé en savepoint. Le pivot ne bloque
        jamais la désactivation user (AC-C.3).
        """
        partner_ids = snapshot.get('partner_ids', [])
        activity_ids = snapshot.get('activity_ids', [])
        schedule_ids = snapshot.get('schedule_ids', [])
        if not partner_ids and not activity_ids:
            return  # rien à faire
        Partner = self.env['res.partner'].sudo()
        Activity = self.env['mail.activity'].sudo()
        activities = Activity.browse(activity_ids).exists()
        schedules = self.sudo().browse(schedule_ids).exists()

        # Regrouper les activités par partner concerné
        activities_by_partner = {}
        orphan_activities = self.env['mail.activity']
        for activity in activities:
            if activity.res_model == 'res.partner':
                partner_id = activity.res_id
            elif activity.res_model == 'optical.followup.schedule.line':
                line = self.env['optical.followup.schedule.line'].sudo().browse(activity.res_id).exists()
                partner_id = line.schedule_id.partner_id.id if line else False
            else:
                partner_id = False
            if not partner_id:
                continue
            activities_by_partner.setdefault(partner_id, self.env['mail.activity'])
            activities_by_partner[partner_id] |= activity

        chatters_posted = set()

        for partner_id, acts in activities_by_partner.items():
            partner = Partner.browse(partner_id).exists()
            if not partner:
                continue
            try:
                with self.env.cr.savepoint():
                    new_user = self._resolve_reassignment_target(partner, user)
                    if new_user:
                        acts.write({'user_id': new_user.id})
                        # trace previous_referent (conditional — ne pas écraser
                        # une trace précédente déjà différente)
                        if partner.optical_followup_previous_referent_user_id != user:
                            partner.write({
                                'optical_followup_previous_referent_user_id': user.id,
                            })
                        chatter_body = _(
                            "Référent commercial changé : %(old)s → %(new)s "
                            "(motif : départ / désactivation).",
                            old=user.name,
                            new=new_user.name,
                        )
                    else:
                        orphan_activities |= acts
                        chatter_body = _(
                            "Référent %(old)s désactivé — activité de suivi "
                            "supprimée faute de repreneur identifiable.",
                            old=user.name,
                        )
            except Exception as exc:  # noqa: BLE001 — résilience partner
                _logger.exception(
                    "Sync référent — partner %s ignoré (%s).",
                    partner_id, exc,
                )
                continue
            # Chatter HORS savepoint
            try:
                partner.message_post(body=chatter_body, subtype_xmlid='mail.mt_note')
                chatters_posted.add(partner_id)
            except Exception as exc:  # noqa: BLE001 — chatter non critique
                _logger.exception(
                    "Sync référent — chatter partner %s ignoré (%s).",
                    partner_id, exc,
                )

        # Unlink orphelins (aucun repreneur résolvable — D-COMPLIANCE-DEACTIVATE-BEHAVIOR A)
        if orphan_activities:
            orphan_activities.unlink()

        # Réassignation du referent_user_id sur schedules running ET paused.
        # Sans cela, les schedules running conserveraient le référent inactif :
        # `_materialize_step_activity` créerait les futures activités pour
        # l'ancien user via `_get_effective_followup_user` (helper retourne
        # user inchangé si inactif). Cas croisé SAV inclus (M6).
        for schedule in schedules:
            if schedule.state not in ('running', 'paused'):
                continue
            partner = schedule.partner_id
            if not partner:
                continue
            is_paused = schedule.state == 'paused'
            try:
                with self.env.cr.savepoint():
                    new_user = self._resolve_reassignment_target(partner, user)
                    if new_user:
                        schedule.write({'referent_user_id': new_user.id})
                        if partner.optical_followup_previous_referent_user_id != user:
                            partner.write({
                                'optical_followup_previous_referent_user_id': user.id,
                            })
                        if partner.id not in chatters_posted:
                            if is_paused:
                                partner_body = _(
                                    "Référent commercial changé sur calendrier "
                                    "suspendu : %(old)s → %(new)s. À la reprise, "
                                    "les futures activités seront assignées à %(new)s.",
                                    old=user.name,
                                    new=new_user.name,
                                )
                            else:
                                partner_body = _(
                                    "Référent commercial changé sur calendrier "
                                    "en cours : %(old)s → %(new)s. Les futures "
                                    "activités seront assignées à %(new)s.",
                                    old=user.name,
                                    new=new_user.name,
                                )
                            partner.message_post(
                                body=partner_body,
                                subtype_xmlid='mail.mt_note',
                            )
                            chatters_posted.add(partner.id)
                        try:
                            schedule.message_post(body=_(
                                "Référent commercial changé : %(old)s → %(new)s.",
                                old=user.name,
                                new=new_user.name,
                            ), subtype_xmlid='mail.mt_note')
                        except Exception as exc:  # noqa: BLE001
                            _logger.exception(
                                "Sync référent — chatter schedule %s ignoré (%s).",
                                schedule.id, exc,
                            )
            except Exception as exc:  # noqa: BLE001 — résilience
                _logger.exception(
                    "Sync référent — schedule %s ignoré (%s).",
                    schedule.id, exc,
                )


class OpticalFollowupScheduleLine(models.Model):
    _name = 'optical.followup.schedule.line'
    _description = "Étape matérialisée d'un calendrier de suivi"
    _order = 'schedule_id, sequence, id'

    schedule_id = fields.Many2one(
        'optical.followup.schedule',
        string="Calendrier",
        required=True,
        ondelete='cascade',
        index=True,
    )
    step_id = fields.Many2one(
        'optical.followup.plan.step',
        string="Étape du plan",
        ondelete='restrict',
        help="Étape du plan-type dont cette ligne est la matérialisation.",
    )
    sequence = fields.Integer(default=10)
    date_planned = fields.Date(
        string="Date planifiée",
        help="delivered_date + step.offset_days.",
    )
    date_planned_original = fields.Date(
        string="Date planifiée (initiale)",
        readonly=True,
        help="Copie initiale au create — audit pour futurs décalages (Story 2.1).",
    )
    outcome = fields.Selection(
        [
            ('answered', "Répondu"),
            ('unreachable', "Injoignable"),
            ('refused', "Refusé poliment"),
            ('purchased', "A acheté"),
        ],
        string="Issue du contact",
    )
    outcome_note = fields.Text(string="Commentaire issue")
    holiday_window_id = fields.Many2one(
        'optical.followup.holiday.window',
        string="Fenêtre de vigilance",
        ondelete='set null',
        help="Fenêtre saisonnière ayant impacté la matérialisation "
             "(report ou basculement soft). Renseigné à la 1ʳᵉ passage "
             "par `_apply_holiday_window` — garantit l'idempotence.",
    )
    state = fields.Selection(
        [
            ('pending', "En attente"),
            ('done', "Réalisée"),
            ('skipped', "Ignorée"),
            ('cancelled', "Annulée"),
            ('paused', "Suspendue"),
            ('overdue', "En retard"),
        ],
        string="État",
        default='pending',
        required=True,
    )
    activity_id = fields.Many2one(
        'mail.activity',
        string="Activité Odoo",
        ondelete='set null',
        help="Activité Odoo associée à l'étape (rappel commercial). "
             "Supprimée en cascade lors d'un opt-out client.",
    )
    state_color = fields.Integer(
        string="Couleur (calendrier)",
        compute='_compute_state_color',
        store=False,
        help="Index couleur sémantique pour la vue calendar (Story 17-4 — "
             "H4 revue). Mapping constant : pending=4, overdue=1, done=10, "
             "cancelled=2, skipped=8, paused=3.",
    )
    # ------------------------------------------------------------------
    # Story 17-2 — Related stored pour permettre group_by natif Odoo 18
    # (Odoo 18 refuse group_by='schedule_id.referent_user_id' — filtre
    # search doit pointer un field direct sur le modèle).
    # ------------------------------------------------------------------
    referent_user_id = fields.Many2one(
        'res.users',
        string="Commercial référent",
        related='schedule_id.referent_user_id',
        store=True,
        readonly=True,
        index=True,
        help="Related stored du référent du calendrier (Story 17-2 KPI 1) — "
             "expose le champ en group_by natif Odoo 18.",
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string="Boutique",
        related='schedule_id.warehouse_id',
        store=True,
        readonly=True,
        index=True,
        help="Related stored de la boutique du calendrier (Story 17-2 KPI 1) — "
             "expose le champ en group_by natif Odoo 18.",
    )

    # Mapping sémantique état → couleur calendar Odoo (H4 revue).
    # NE PAS utiliser ``color=state`` directement : Odoo hasherait les
    # valeurs Selection arbitrairement, aucun contrôle sémantique.
    _STATE_COLOR_MAP = {
        'pending': 4,     # bleu
        'overdue': 1,     # rouge
        'done': 10,       # vert
        'cancelled': 2,   # orange
        'skipped': 8,     # gris
        'paused': 3,      # jaune
    }

    @api.depends('state')
    def _compute_state_color(self):
        for line in self:
            line.state_color = self._STATE_COLOR_MAP.get(line.state, 0)

    @api.depends(
        'schedule_id.partner_id.name',
        'step_id.objective',
        'step_id.name',
        'step_id.suggested_channel',
    )
    def _compute_display_name(self):
        """Nom lisible « Client — Objectif (Canal) » (format 2B).

        Remplace le fallback technique ``optical.followup.schedule.line,<id>``
        affiché comme titre d'événement dans la vue calendar (planning des
        étapes) et partout où une étape est référencée. Robuste aux champs
        manquants (client / objectif / canal absents).
        """
        for line in self:
            partner = line.schedule_id.partner_id.name or _("Client")
            label = (
                line.step_id.objective
                or line.step_id.name
                or _("Étape")
            )
            channel = line.step_id.suggested_channel
            channel_label = ''
            if channel:
                channel_label = dict(
                    line.step_id._fields['suggested_channel']
                    ._description_selection(self.env)
                ).get(channel, '')
            if channel_label:
                line.display_name = "%s — %s (%s)" % (partner, label, channel_label)
            else:
                line.display_name = "%s — %s" % (partner, label)

    # ==================================================================
    # Matérialisation d'une mail.activity (AC3) + fenêtres (Story 16-1)
    # ==================================================================

    _POSTPONE_CASCADE_MAX = 3

    def _apply_holiday_window(self, step):
        """Évalue les fenêtres actives à ``self.date_planned``.

        Idempotence : si ``self.holiday_window_id`` est déjà renseigné,
        aucune ré-évaluation (2ᵉ passage cron après report).

        Applique le comportement retenu (AC6-AC9) :
          - ``postpone_to_end`` : déplace ``date_planned`` à
            ``date_end + 1 j``, renseigne ``holiday_window_id``, poste
            un chatter sur le partner. **Cascade** : si la nouvelle date
            retombe dans une autre fenêtre ``postpone_to_end`` adjacente
            (ex. PO configurant Ramadan et Aïd al-Fitr tous deux en
            postpone), la ligne est repoussée à nouveau jusqu'à trouver
            une date libre — max ``_POSTPONE_CASCADE_MAX`` itérations.
          - ``switch_channel_soft`` : garde ``date_planned``, renseigne
            ``holiday_window_id``, aucun chatter.
          - ``none`` : aucun effet fonctionnel, ``holiday_window_id``
            reste vide (pas de traçabilité).

        Retourne un dict consommé par ``_materialize_step_activity`` pour
        enrichir la note et poster le chatter le cas échéant :
          ``{'window': window_recordset, 'behavior': str|None, 'shifted': bool}``
        """
        self.ensure_one()
        if self.holiday_window_id:
            # 2ᵉ passage cron : la fenêtre a déjà été appliquée en 1ʳᵉ passe.
            return {
                'window': self.holiday_window_id,
                'behavior': self.holiday_window_id.behavior,
                'shifted': False,
            }

        Window = self.env['optical.followup.holiday.window']
        original = self.date_planned
        current_date = original
        current_window = None
        cascade_windows = []

        for _iteration in range(self._POSTPONE_CASCADE_MAX):
            match = Window._find_applicable(current_date)
            if not match:
                break
            window, _start, end = match
            if window.behavior != 'postpone_to_end':
                # Cascade se termine sur une fenêtre non-postpone. Si une
                # cascade postpone a déjà eu lieu, on conserve la dernière
                # fenêtre postpone comme trace (la ligne est ancrée hors
                # de sa période initiale) — sinon, priorité au 1ᵉʳ hit.
                if not cascade_windows:
                    current_window = window
                break
            cascade_windows.append(window)
            current_date = fields.Date.add(end, days=1)
            current_window = window
        else:
            # `else` d'un `for` : atteint uniquement si la boucle épuise
            # ``_POSTPONE_CASCADE_MAX`` sans `break` — cascade anormale.
            _logger.warning(
                "Ligne %s : cascade postpone > %s itérations à partir de %s, "
                "matérialisation à %s (dernière fenêtre : %s).",
                self.id, self._POSTPONE_CASCADE_MAX, original, current_date,
                current_window.name if current_window else '-',
            )

        if not current_window:
            return {'window': Window.browse(), 'behavior': None, 'shifted': False}

        if current_window.behavior == 'none':
            # Aucun effet fonctionnel — pas de traçabilité (AC8).
            return {'window': current_window, 'behavior': 'none', 'shifted': False}

        if cascade_windows:
            # Postpone effectif (1 ou plusieurs sauts).
            self.sudo().write({
                'date_planned': current_date,
                'holiday_window_id': current_window.id,
            })
            partner = self.schedule_id.partner_id
            partner.sudo().message_post(body=_(
                "Étape « %(step)s » reportée du %(from_date)s au %(to_date)s "
                "— fenêtre %(window)s.",
                step=step.name,
                from_date=fields.Date.to_string(original),
                to_date=fields.Date.to_string(current_date),
                window=current_window.name,
            ))
            return {'window': current_window, 'behavior': 'postpone_to_end', 'shifted': True}

        # switch_channel_soft : traçabilité sans décalage.
        self.sudo().write({'holiday_window_id': current_window.id})
        return {'window': current_window, 'behavior': 'switch_channel_soft', 'shifted': False}

    def _materialize_step_activity(self):
        """Crée la ``mail.activity`` J-3 sur le partner du schedule.

        Idempotence : si ``activity_id`` déjà renseigné, no-op.
        Le champ ``activity_id`` est renseigné à la sortie.

        Depuis Story 16-1 : applique en tête ``_apply_holiday_window`` qui
        peut reporter ``date_planned`` (postpone) ou signaler un
        basculement de canal (switch_channel_soft) — la note d'activité
        est enrichie en conséquence.
        """
        self.ensure_one()
        if self.activity_id:
            return self.activity_id
        step = self.step_id
        if not step or not step.activity_type_id:
            _logger.warning(
                "Ligne %s : step ou activity_type manquant — matérialisation ignorée.",
                self.id,
            )
            return self.env['mail.activity']

        window_info = self._apply_holiday_window(step)

        partner = self.schedule_id.partner_id
        referent = self.schedule_id.referent_user_id or self.env.user
        # Story 17-3 AC-E.3 : aller-simple vers suppléant si le titulaire
        # est en absence longue active — évite un create-then-update coûteux.
        referent = self.env['res.users']._get_effective_followup_user(referent)
        model_partner = self.env['ir.model']._get('res.partner')

        note_parts = []
        if step.description:
            note_parts.append(plaintext2html(step.description))
        channel_label = dict(
            step._fields['suggested_channel']._description_selection(self.env)
        ).get(step.suggested_channel, '') if step.suggested_channel else ''
        role_label = dict(
            step._fields['suggested_role']._description_selection(self.env)
        ).get(step.suggested_role, '') if step.suggested_role else ''
        if channel_label or role_label:
            hint = _(
                "Canal recommandé : %(channel)s. Rôle recommandé : %(role)s.",
                channel=channel_label or _("(non précisé)"),
                role=role_label or _("(non précisé)"),
            )
            note_parts.append("<p>%s</p>" % hint)
        if step.mail_template_id:
            note_parts.append("<p>%s</p>" % _(
                "Template mail suggéré : %s", step.mail_template_id.name,
            ))

        # Enrichissement de la note selon le comportement de fenêtre.
        window = window_info['window']
        behavior = window_info['behavior']
        if window and behavior == 'postpone_to_end' and window_info['shifted']:
            original_date = self.date_planned_original or self.date_planned
            note_parts.append("<p>%s</p>" % _(
                "Reporté par fenêtre %(window)s (période initiale %(original)s).",
                window=window.name,
                original=fields.Date.to_string(original_date),
            ))
        elif window and behavior == 'switch_channel_soft':
            win_channel_label = dict(
                window._fields['suggested_channel']._description_selection(self.env)
            ).get(window.suggested_channel, '') if window.suggested_channel else ''
            if win_channel_label and win_channel_label != channel_label:
                note_parts.append("<p>%s</p>" % _(
                    "Période %(window)s : préférer %(win_channel)s plutôt "
                    "que %(step_channel)s.",
                    window=window.name,
                    win_channel=win_channel_label,
                    step_channel=channel_label or _("(non précisé)"),
                ))
            else:
                note_parts.append("<p>%s</p>" % _(
                    "Période %(window)s : privilégier WhatsApp ou email "
                    "plutôt que %(step_channel)s.",
                    window=window.name,
                    step_channel=channel_label or _("(non précisé)"),
                ))

        note_html = "".join(note_parts) or ""

        activity = self.env['mail.activity'].sudo().create({
            'res_model': 'res.partner',
            'res_model_id': model_partner.id,
            'res_id': partner.id,
            'activity_type_id': step.activity_type_id.id,
            'user_id': referent.id,
            'summary': step.objective or step.name,
            'note': note_html,
            'date_deadline': self.date_planned,
        })
        self.sudo().write({'activity_id': activity.id})
        return activity

    # ==================================================================
    # Clôture par le commercial via wizard outcome (AC5)
    # ==================================================================

    def _mark_done(self, outcome, note=None):
        """Marque la ligne ``done`` avec un outcome + commentaire optionnel.

        Renseigne ``schedule.first_contact_date`` si c'est la 1ʳᵉ ligne done
        du calendrier (support KPI 4 — Story 3.2).
        Ferme l'activité Odoo native (``action_feedback``).
        """
        self.ensure_one()
        if outcome not in ('answered', 'unreachable', 'refused', 'purchased'):
            raise ValueError("Outcome invalide : %s" % outcome)
        # Garde-fou : refuser un 2ᵉ appel qui écraserait un outcome existant
        # (le wizard peut être rejoué par erreur — cf. code review S15.2).
        if self.state not in ('pending', 'overdue'):
            raise UserError(_(
                "Cette étape a déjà été clôturée (état : %s).", self.state,
            ))

        vals = {
            'state': 'done',
            'outcome': outcome,
        }
        if note:
            vals['outcome_note'] = note
        self.sudo().write(vals)

        schedule = self.schedule_id
        if not schedule.first_contact_date:
            other_done = schedule.line_ids.filtered(
                lambda l: l.id != self.id and l.state == 'done'
            )
            if not other_done:
                schedule.sudo().write({
                    'first_contact_date': fields.Date.today(),
                })

        if self.activity_id:
            self.activity_id.sudo().action_feedback(feedback=note or '')
        return True
