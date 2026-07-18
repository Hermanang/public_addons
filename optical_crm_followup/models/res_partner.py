# -*- coding: utf-8 -*-
import base64
import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

# Seuil de majorité (Sénégal — 18 ans). Approximation en jours pour éviter la
# dépendance à dateutil (voir Notes développeur story 15.1).
_ADULT_THRESHOLD_DAYS = 18 * 365.25

# Champs autorisés en écriture sur un partner anonymisé (Story 17-3 AC-B.3).
# ``parent_id`` et ``active`` restent modifiables pour ne pas casser les
# opérations comptables Odoo natives (désactivation partner, restructuration).
_ANONYMIZED_WRITABLE_FIELDS = frozenset({'parent_id', 'active'})


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ------------------------------------------------------------------
    # Consentement de suivi
    # ------------------------------------------------------------------

    optical_followup_consent = fields.Boolean(
        string="Consentement suivi optique",
        help="Coché par le commercial lorsque le client a signé la case sur le "
             "bon de commande papier. Sans consentement, aucun calendrier de "
             "suivi ne peut démarrer (Loi 2008-12 art. 33).",
    )
    optical_followup_consent_date = fields.Date(
        string="Date consentement",
        readonly=True,
        help="Horodatage automatique de la dernière coche du consentement.",
    )
    optical_followup_consent_by_id = fields.Many2one(
        'res.users',
        string="Consentement recueilli par",
        readonly=True,
        ondelete='restrict',
        help="Utilisateur ayant coché le consentement — traçabilité chatter.",
    )
    optical_followup_consent_by_legal_rep = fields.Boolean(
        string="Consentement représentant légal",
        help="Coché par le commercial pour un client mineur lorsque le parent "
             "ou représentant légal a signé le bon de commande.",
    )

    # ------------------------------------------------------------------
    # Opposition (opt-out)
    # ------------------------------------------------------------------

    optical_followup_optout = fields.Boolean(
        string="Opposition au suivi",
        help="Coché lorsque le client demande à ne plus recevoir de messages "
             "de suivi. La cascade est immédiate : calendriers en cours "
             "annulés, activités pendantes supprimées, futures créations "
             "verrouillées (NFR-04 < 60 s).",
    )
    optical_followup_optout_date = fields.Date(
        string="Date opposition",
        readonly=True,
    )
    optical_followup_optout_reason = fields.Char(
        string="Motif opposition",
        help="Motif recommandé mais non obligatoire (la Loi 2008-12 n'oblige "
             "pas le client à justifier son opposition).",
    )

    # ------------------------------------------------------------------
    # Continuité RH & compliance étendue (Story 17-3)
    # ------------------------------------------------------------------

    optical_followup_previous_referent_user_id = fields.Many2one(
        'res.users',
        string="Ancien référent (trace)",
        ondelete='set null',
        readonly=True,
        help="Trace du dernier référent avant réattribution (départ, absence "
             "longue ou action manager). Réinitialisé après nouvelle "
             "réattribution — sert à l'audit continuité RH (Story 17-3 AC-C / "
             "AC-F). FR-21.",
    )
    optical_followup_majority_request_date = fields.Date(
        string="Date demande consentement majeur",
        readonly=True,
        help="Date d'envoi du mail de renouvellement de consentement à la "
             "majorité (Story 17-3 AC-A). Write-once soft : réécriture "
             "silencieusement ignorée si déjà renseignée. Conservée après "
             "confirmation manuelle (audit).",
    )
    optical_anonymized = fields.Boolean(
        string="Fiche anonymisée",
        default=False,
        readonly=True,
        help="True si la fiche a été anonymisée par le dispositif de "
             "fidélisation (Story 17-3 AC-B, NFR-14 write-once). Une fois "
             "posé, l'accès en écriture est verrouillé — le seul bypass "
             "reste ``sudo()`` (rollback support, journalisé en warning).",
    )
    optical_anonymized_date = fields.Date(
        string="Date d'anonymisation",
        readonly=True,
        help="Date à laquelle la fiche a été anonymisée. Ne PAS effacer même "
             "si le partner est ré-anonymisé (opération unique — NFR-14).",
    )

    # ------------------------------------------------------------------
    # Tier client configurable (Story 18-1 — FR-11, refonte de 17-1)
    # ------------------------------------------------------------------

    optical_customer_tier_override_id = fields.Many2one(
        'optical.customer.tier',
        string="Forcer un tier (override manager)",
        ondelete='restrict',
        help="Renseigné par un responsable pour forcer le tier d'un client à "
             "une valeur précise, indépendamment du cumul CA. Prend le pas "
             "sur le calcul automatique. Écriture réservée au groupe "
             "``optical.group_optical_manager`` (garde-fou Python + vue). "
             "Story 18-1 AC-3.",
    )
    optical_customer_tier_id = fields.Many2one(
        'optical.customer.tier',
        string="Tier client",
        compute='_compute_optical_customer_tier',
        store=True,
        readonly=True,
        index=True,
        ondelete='restrict',
        help="Tier de fidélisation du client. Égal à l'override manager s'il "
             "est renseigné, sinon calculé automatiquement : le tier de plus "
             "haut seuil dont le ``threshold_fcfa`` est atteint par le CA "
             "cumulé (TTC) des ``sale.order`` en état ``sale`` ou ``done`` ; "
             "à défaut, le tier marqué « par défaut ». Story 18-1 AC-2.",
    )

    # ------------------------------------------------------------------
    # Référent effectif (Story 17-2 AC-5 — mitigation R2 archi)
    # ------------------------------------------------------------------

    optical_referent_user_id = fields.Many2one(
        'res.users',
        string="Référent effectif",
        compute='_compute_optical_referent_user_id',
        store=True,
        readonly=True,
        ondelete='set null',
        index=True,
        help="Référent effectif du client : user_id manuel s'il est "
             "renseigné, sinon fallback sur le user_id de la SO la plus "
             "récente en état sale/done. Sert à identifier les clients "
             "sans référent (mitigation R2 archi — Story 17-2 AC-5).",
    )
    optical_has_confirmed_so = fields.Boolean(
        string="A une commande confirmée",
        compute='_compute_optical_has_confirmed_so',
        store=True,
        readonly=True,
        help="True si le partner a au moins une sale.order en état sale/done. "
             "Sert au domain de la vue « Clients sans référent » pour exclure "
             "les partners qui n'ont eu que des SO annulées/brouillon (revue "
             "H2 S17-2 — sale_order_count non-searchable en Odoo natif).",
    )

    # ------------------------------------------------------------------
    # État calculé (affichage — non stocké)
    # ------------------------------------------------------------------

    optical_followup_state = fields.Selection(
        [
            ('never', "Jamais démarré"),
            ('active', "En cours"),
            ('paused', "Suspendu"),
            ('done', "Abouti"),
            ('optout', "En opposition"),
        ],
        string="Statut suivi",
        compute='_compute_optical_followup_state',
        store=False,
    )

    # ==================================================================
    # Compute
    # ==================================================================

    # ------------------------------------------------------------------
    # Story 18-1 AC-2 — Compute du tier client (N tiers configurables)
    # ------------------------------------------------------------------

    @api.depends(
        'optical_customer_tier_override_id',
        'sale_order_ids.state',
        'sale_order_ids.amount_total',
    )
    def _compute_optical_customer_tier(self):
        """Story 18-1 AC-2/AC-3 — calcul stored du tier parmi N tiers.

        Règle :
          - ``optical_customer_tier_override_id`` renseigné → ce tier (prime).
          - Sinon : ``sum(so.amount_total)`` pour ``so.state in ('sale','done')``
            comparé aux seuils des tiers → le tier NON-défaut de plus haut
            ``threshold_fcfa`` tel que ``threshold_fcfa <= CA`` (sémantique
            AC-2.2). À défaut, le tier marqué « par défaut ».

        Batch-safe (AC-2.3) : une seule ``search`` sur ``optical.customer.tier``
        et un seul ``read_group`` sur ``sale.order`` regroupé par
        ``partner_id`` — pas de N+1 sur un batch de recompute.

        Le recompute sur changement de seuil/rang d'un tier (AC-2.4) est
        déclenché par l'override ``write`` de ``optical.customer.tier``
        (``_trigger_partner_tier_recompute``) : les seuils appartenant à un
        autre modèle, ils ne peuvent pas figurer dans ``@api.depends``.

        NOTE multi-company (repris S17-1 M6) : le read_group ne filtre PAS
        ``company_id`` — neutre en mono-company Luxe Optique. Ajouter
        ``('company_id', 'in', self.env.companies.ids)`` en multi-company.
        """
        Tier = self.env['optical.customer.tier'].sudo()
        active_tiers = Tier.search([])  # exclut les tiers archivés
        default_tier = active_tiers.filtered('is_default')[:1]

        # Tiers non-défaut à seuil valide (> 0), triés par seuil croissant.
        threshold_tiers = active_tiers.filtered(
            lambda t: not t.is_default and t.threshold_fcfa > 0
        ).sorted('threshold_fcfa')
        # AC-5.2 — un tier non-défaut à seuil <= 0 n'a pas de sens : ignoré,
        # anomalie tracée (config-level, donc rare).
        for bad in active_tiers.filtered(
            lambda t: not t.is_default and t.threshold_fcfa <= 0
        ):
            _logger.warning(
                "Tier %s (id %s) non-défaut avec seuil <= 0 (%s) — ignoré au "
                "calcul du tier client.",
                bad.name, bad.id, bad.threshold_fcfa,
            )

        # read_group batch du CA cumulé pour tous les partners self.
        so_totals = {}
        if self.ids:
            grouped = self.env['sale.order'].sudo().read_group(
                domain=[
                    ('partner_id', 'in', self.ids),
                    ('state', 'in', ('sale', 'done')),
                ],
                fields=['partner_id', 'amount_total:sum'],
                groupby=['partner_id'],
            )
            for row in grouped:
                partner_id = row['partner_id'][0] if row['partner_id'] else False
                if partner_id:
                    so_totals[partner_id] = row['amount_total'] or 0.0

        for partner in self:
            override = partner.optical_customer_tier_override_id
            if override:
                partner.optical_customer_tier_id = override
                continue
            total = so_totals.get(partner.id, 0.0)
            # threshold_tiers trié croissant : le dernier dont le seuil est
            # atteint est le tier de plus haut seuil applicable.
            matched = default_tier
            for tier in threshold_tiers:
                if tier.threshold_fcfa <= total:
                    matched = tier
                else:
                    break
            partner.optical_customer_tier_id = matched

    # ------------------------------------------------------------------
    # Story 17-2 AC-5.1 — Compute optical_referent_user_id (batch-safe)
    # ------------------------------------------------------------------

    @api.depends(
        'user_id',
        'sale_order_ids.user_id',
        'sale_order_ids.state',
        'sale_order_ids.date_order',
    )
    def _compute_optical_referent_user_id(self):
        """Story 17-2 AC-5.1 — matérialisation stored du référent effectif.

        Règle :
          1. ``partner.user_id`` (référent manuel Odoo natif) — cohérent
             avec ``_get_followup_referent``
          2. Sinon, ``user_id`` de la SO la plus récente du partner en état
             ``sale`` ou ``done``
          3. Sinon, ``False`` (aucun référent identifiable)

        Batch-safe : une seule ``search_read`` sur ``sale.order`` pour tous
        les partners sans ``user_id`` manuel — évite le N+1 sur un batch de
        recompute déclenché par un write cascade (revue adversariale Task 9.1).
        """
        UserModel = self.env['res.users']
        # Étape 1 : ceux qui ont un user_id manuel — passthrough direct.
        with_manual = self.filtered('user_id')
        for partner in with_manual:
            partner.optical_referent_user_id = partner.user_id

        remaining = self - with_manual
        if not remaining:
            return

        # Étape 2 : recherche batch de la dernière SO éligible par partner.
        rows = self.env['sale.order'].sudo().search_read(
            domain=[
                ('partner_id', 'in', remaining.ids),
                ('state', 'in', ('sale', 'done')),
                ('user_id', '!=', False),
            ],
            fields=['partner_id', 'user_id'],
            order='partner_id, date_order desc, id desc',
        )
        so_map = {}
        for row in rows:
            pid = row['partner_id'][0] if row['partner_id'] else False
            if pid and pid not in so_map:
                # La première row par partner est la plus récente
                # (order='partner_id, date_order desc').
                uid = row['user_id'][0] if row['user_id'] else False
                so_map[pid] = uid

        for partner in remaining:
            uid = so_map.get(partner.id)
            partner.optical_referent_user_id = (
                UserModel.browse(uid) if uid else UserModel
            )

    @api.depends('sale_order_ids.state')
    def _compute_optical_has_confirmed_so(self):
        """Story 17-2 AC-5 (revue H2) — True si au moins 1 SO confirmée.

        Batch-safe : 1 seul read_group sur ``sale.order`` regroupé par
        ``partner_id``, dispatch en Python. Évite le N+1 sur un batch de
        recompute déclenché par un cascade write sale.order (typique lors
        d'un ``action_confirm`` en masse).
        """
        if not self:
            return
        confirmed_partner_ids = set()
        if self.ids:
            grouped = self.env['sale.order'].sudo().read_group(
                domain=[
                    ('partner_id', 'in', self.ids),
                    ('state', 'in', ('sale', 'done')),
                ],
                fields=['partner_id'],
                groupby=['partner_id'],
            )
            confirmed_partner_ids = {
                row['partner_id'][0] for row in grouped if row['partner_id']
            }
        for partner in self:
            partner.optical_has_confirmed_so = partner.id in confirmed_partner_ids

    @api.depends('optical_followup_consent', 'optical_followup_optout')
    def _compute_optical_followup_state(self):
        # Batch : un seul SELECT quel que soit le nombre de partners lus
        # (évite le N+1 quand le champ est projeté sur une vue liste ou un
        # export).
        schedules = self.env['optical.followup.schedule'].search(
            [('partner_id', 'in', self.ids)],
            order='create_date desc, id desc',
        )
        last_by_partner = {}
        for schedule in schedules:
            last_by_partner.setdefault(schedule.partner_id.id, schedule)

        for partner in self:
            if partner.optical_followup_optout:
                partner.optical_followup_state = 'optout'
                continue
            if not partner.optical_followup_consent:
                partner.optical_followup_state = 'never'
                continue
            last = last_by_partner.get(partner.id)
            if not last:
                partner.optical_followup_state = 'never'
            elif last.state == 'running':
                partner.optical_followup_state = 'active'
            elif last.state == 'paused':
                partner.optical_followup_state = 'paused'
            elif last.state == 'fulfilled':
                partner.optical_followup_state = 'done'
            else:
                partner.optical_followup_state = 'never'

    # ==================================================================
    # Helper d'éligibilité — signature stable pour Story 15.2 (hook picking)
    # ==================================================================

    def _can_start_followup(self):
        """Détermine si un partner est éligible à un démarrage de calendrier.

        Retourne un tuple ``(bool, reason_code)`` avec ``reason_code`` dans
        ``{None, 'no_consent', 'optout', 'minor_no_legal_rep'}``.
        """
        self.ensure_one()
        if not self.optical_followup_consent:
            return (False, 'no_consent')
        if self.optical_followup_optout:
            return (False, 'optout')
        if self.birthdate:
            age_days = (fields.Date.today() - self.birthdate).days
            if age_days < _ADULT_THRESHOLD_DAYS and not self.optical_followup_consent_by_legal_rep:
                return (False, 'minor_no_legal_rep')
        else:
            _logger.info(
                "Éligibilité followup: partner %s %s sans birthdate — présumé majeur.",
                self.id, self.name,
            )
        return (True, None)

    # ==================================================================
    # Helper de résolution du référent commercial (Story 15.2 AC1)
    # ==================================================================

    def _get_followup_referent(self, sale_order=None):
        """Résout le commercial référent pour un nouveau calendrier de suivi.

        Heuristique :
          1. ``partner.user_id`` si renseigné (commercial dédié au client)
          2. ``sale_order.user_id`` du picking à l'origine
          3. Fallback recordset vide (référent None — cron digest skip)

        La réattribution en cas de départ commercial est portée par Story 3.3.
        """
        self.ensure_one()
        if self.user_id:
            return self.user_id
        if sale_order and sale_order.user_id:
            return sale_order.user_id
        return self.env['res.users']

    # ==================================================================
    # Override write — horodatage auto + cascade opt-out + write-once anonym.
    # ==================================================================

    def _check_anonymized_write(self, vals):
        """Story 17-3 AC-B.3 — write-once sur partner anonymisé.

        Refuse toute modification d'un partner ``optical_anonymized=True``
        sauf pour les champs whitelistés (``parent_id``, ``active`` —
        nécessaires aux opérations Odoo natives) et sauf ``sudo()`` (bypass
        support journalisé en warning).

        Bloque également le cas de contournement (revue S17-3 M7) : un
        caller qui pose ``optical_anonymized=True`` en même temps que
        d'autres champs (hors whitelist et context flag) tenterait
        d'écrire des données sur une fiche qu'il est en train d'anonymiser
        — l'anonymisation doit passer par ``_anonymize_for_followup``
        exclusivement.
        """
        if self.env.context.get('optical_anonymize_in_progress'):
            return
        touched_fields = set(vals.keys()) - _ANONYMIZED_WRITABLE_FIELDS

        # Cas 1 : partner(s) déjà anonymisé(s) — refus classique
        anonymized = self.filtered('optical_anonymized')
        if anonymized and touched_fields:
            if self.env.su:
                _logger.warning(
                    "Anonymisation write-once bypass via sudo() — partner(s) %s, "
                    "champs %s. Bypass admin uniquement (rollback support).",
                    anonymized.ids, sorted(touched_fields),
                )
            else:
                raise UserError(_(
                    "Fiche client anonymisée le %(date)s — modification interdite "
                    "(write-once, obligation CDP art. 65-71). Champs concernés : %(fields)s.",
                    date=fields.Date.to_string(
                        anonymized[:1].optical_anonymized_date or fields.Date.today()
                    ),
                    fields=", ".join(sorted(touched_fields)),
                ))

        # Cas 2 : bascule inline optical_anonymized=True + autres champs hors
        # `_anonymize_for_followup` — bypass de la voie canonique (revue M7).
        # Autorisé uniquement en sudo (rollback support, journalisé warning).
        setting_anonymized = vals.get('optical_anonymized') is True
        other_fields = touched_fields - {'optical_anonymized'}
        if setting_anonymized and other_fields:
            if self.env.su:
                _logger.warning(
                    "Anonymisation write inline (optical_anonymized=True + %s) "
                    "sur partner(s) %s en dehors de _anonymize_for_followup. "
                    "Bypass admin uniquement (journalisé pour audit CDP).",
                    sorted(other_fields), self.ids,
                )
            else:
                raise UserError(_(
                    "L'anonymisation d'une fiche client doit passer par "
                    "``partner._anonymize_for_followup(reason)`` — la bascule "
                    "``optical_anonymized=True`` combinée à d'autres champs "
                    "(%(fields)s) est interdite en dehors de cette voie.",
                    fields=", ".join(sorted(other_fields)),
                ))

    @api.model_create_multi
    def create(self, vals_list):
        # Story 18-1 AC-3.2 (revue 2026-07-18, M1) — même garde-fou que
        # ``write`` : ``create`` ne doit pas être une porte dérobée pour poser
        # l'override de tier. La vue masque le champ aux non-managers, mais un
        # caller ORM / import CSV / API contournerait la vue. Bypass ``sudo()``
        # conservé (cron / migration).
        if (
            not self.env.su
            and not self.env.user.has_group('optical.group_optical_manager')
            and any(v.get('optical_customer_tier_override_id') for v in vals_list)
        ):
            raise AccessError(_(
                "Seul un responsable peut forcer le tier d'un client "
                "(champ ``optical_customer_tier_override_id``)."
            ))
        return super().create(vals_list)

    def write(self, vals):
        self._check_anonymized_write(vals)

        # Story 18-1 AC-3.2 — garde-fou Python override tier (manager only).
        # Défense en profondeur : la vue XML expose ``groups="…manager"``
        # mais un caller ORM (script, wizard, tests) pourrait contourner.
        # Le bypass ``sudo()`` reste possible (cas cron / migration).
        if (
            'optical_customer_tier_override_id' in vals
            and not self.env.su
            and not self.env.user.has_group('optical.group_optical_manager')
        ):
            raise AccessError(_(
                "Seul un responsable peut forcer le tier d'un client "
                "(champ ``optical_customer_tier_override_id``)."
            ))

        # Story 18-1 AC-3.3 — capturer la bascule override pour chatter.
        override_toggled = {}  # partner.id → (before_id, after_id) si bascule
        if 'optical_customer_tier_override_id' in vals:
            new_value = vals['optical_customer_tier_override_id'] or False
            for partner in self:
                before = partner.optical_customer_tier_override_id.id or False
                if before != new_value:
                    override_toggled[partner.id] = (before, new_value)

        # Story 17-3 AC-A : write-once soft sur majority_request_date.
        # En batch homogène : pop silencieux de la clé si tous déjà datés.
        # En batch mixte (certains datés, d'autres non) : split récursif —
        # sinon les partners already_set seraient silencieusement écrasés
        # (revue S17-3 H3). Le cron interne utilise sudo, non affecté.
        if (
            'optical_followup_majority_request_date' in vals
            and not self.env.su
        ):
            already_set = self.filtered('optical_followup_majority_request_date')
            if already_set:
                if already_set == self:
                    vals = {
                        k: v for k, v in vals.items()
                        if k != 'optical_followup_majority_request_date'
                    }
                    if not vals:
                        return True
                else:
                    not_yet_set = self - already_set
                    vals_stripped = {
                        k: v for k, v in vals.items()
                        if k != 'optical_followup_majority_request_date'
                    }
                    if not_yet_set:
                        not_yet_set.write(vals)
                    if vals_stripped and already_set:
                        already_set.write(vals_stripped)
                    return True

        consent_key = 'optical_followup_consent'
        optout_key = 'optical_followup_optout'

        consent_toggled_on = {}  # partner.id → True si bascule False→True
        optout_toggled_on = {}   # partner.id → True si bascule False→True

        if consent_key in vals or optout_key in vals:
            for partner in self:
                if (
                    consent_key in vals
                    and vals[consent_key]
                    and not partner.optical_followup_consent
                ):
                    consent_toggled_on[partner.id] = True
                if (
                    optout_key in vals
                    and vals[optout_key]
                    and not partner.optical_followup_optout
                ):
                    optout_toggled_on[partner.id] = True

        # Enrichir vals avec les auto-timestamps si un seul partner concerné.
        # Assignation directe (pas setdefault) — les champs d'horodatage
        # sont audit CDP : un caller ne doit pas pouvoir antidater le
        # consentement en posant sa propre date dans vals.
        auto_vals = dict(vals)
        if len(consent_toggled_on) == len(self) and consent_toggled_on:
            auto_vals['optical_followup_consent_date'] = fields.Date.context_today(self)
            auto_vals['optical_followup_consent_by_id'] = self.env.user.id
        if len(optout_toggled_on) == len(self) and optout_toggled_on:
            auto_vals['optical_followup_optout_date'] = fields.Date.context_today(self)

        result = super().write(auto_vals)

        # Cas mixte (plusieurs partners avec bascules hétérogènes) : compléter
        # les auto-timestamps partner par partner (idem : override forcé).
        if consent_toggled_on and len(consent_toggled_on) != len(self):
            for partner in self.filtered(lambda p: consent_toggled_on.get(p.id)):
                super(ResPartner, partner).write({
                    'optical_followup_consent_date': fields.Date.context_today(self),
                    'optical_followup_consent_by_id': self.env.user.id,
                })
        if optout_toggled_on and len(optout_toggled_on) != len(self):
            for partner in self.filtered(lambda p: optout_toggled_on.get(p.id)):
                super(ResPartner, partner).write({
                    'optical_followup_optout_date': fields.Date.context_today(self),
                })

        # Chatter + cascade — après la persistance des champs
        for partner in self:
            if consent_toggled_on.get(partner.id):
                partner.message_post(
                    body=_(
                        "Consentement de suivi enregistré le %(date)s par %(user)s.",
                        date=fields.Date.to_string(partner.optical_followup_consent_date),
                        user=partner.optical_followup_consent_by_id.name or self.env.user.name,
                    )
                )
            if optout_toggled_on.get(partner.id):
                reason = vals.get(
                    'optical_followup_optout_reason',
                    partner.optical_followup_optout_reason,
                ) or ''
                schedules = self.env['optical.followup.schedule'].sudo().search(
                    [('partner_id', '=', partner.id)]
                )
                cnt_schedules, cnt_activities = schedules.action_cancel_for_optout(
                    reason
                )
                partner.message_post(
                    body=_(
                        "Opposition enregistrée le %(date)s par %(user)s. "
                        "Raison : %(reason)s. "
                        "%(count_s)s calendrier(s) annulé(s), "
                        "%(count_a)s activité(s) pendante(s) supprimée(s).",
                        date=fields.Date.to_string(partner.optical_followup_optout_date),
                        user=self.env.user.name,
                        reason=reason or _("(non précisée)"),
                        count_s=cnt_schedules,
                        count_a=cnt_activities,
                    )
                )
            # Story 18-1 AC-3.3 — chatter bascule override tier (nom du tier).
            toggle = override_toggled.get(partner.id)
            if toggle:
                _before_id, after_id = toggle
                if after_id:
                    tier_name = self.env['optical.customer.tier'].browse(
                        after_id
                    ).name or _("(tier)")
                    body = _(
                        "Tier client forcé sur « %(tier)s » par override "
                        "manuel (Manager : %(user)s).",
                        tier=tier_name,
                        user=self.env.user.name,
                    )
                else:
                    body = _(
                        "Override de tier retiré — tier recalculé "
                        "automatiquement (Manager : %(user)s).",
                        user=self.env.user.name,
                    )
                try:
                    partner.message_post(
                        body=body,
                        subtype_xmlid='mail.mt_note',
                    )
                except Exception as exc:  # noqa: BLE001 — chatter non critique
                    _logger.exception(
                        "Chatter bascule override tier partner %s ignoré (%s).",
                        partner.id, exc,
                    )

        return result

    # ==================================================================
    # AC-A.3 — Bouton confirmation consentement majeur (Story 17-3)
    # ==================================================================

    def action_optical_followup_confirm_majority(self):
        """Confirme le consentement personnel d'un client devenu majeur.

        Story 17-3 AC-A.3 — manager uniquement (ACL Python en garde-fou).

        Effets en une transaction par partner :
          - ``optical_followup_consent_by_legal_rep`` → False
          - ``optical_followup_consent`` → True (cascade S15.1 pose la date
            + user via l'override ``write`` ci-dessus)
          - Chaque schedule ``paused / majority_pending`` du partner passe
            en ``running`` via ``_resume_from_majority_pending`` (schedules
            paused pour autre motif ne sont pas touchés — garde-fou)
          - Chatter partner + chatter chaque schedule concerné (subtype mt_note)
          - ``optical_followup_majority_request_date`` conservé (audit)
        """
        if not self.env.user.has_group('optical.group_optical_manager'):
            raise AccessError(_(
                "Seul un responsable peut confirmer le consentement d'un "
                "client devenu majeur."
            ))
        Schedule = self.env['optical.followup.schedule'].sudo()
        for partner in self:
            if not partner.optical_followup_majority_request_date:
                continue
            if not partner.optical_followup_consent_by_legal_rep:
                continue
            # 1. Bascule consentement légal → personnel (cascade S15.1
            #    pose consent_date + consent_by_id via override write).
            partner.sudo().write({
                'optical_followup_consent_by_legal_rep': False,
                'optical_followup_consent': True,
            })
            # 2. Reprendre uniquement les schedules paused pour majority_pending.
            schedules = Schedule.search([
                ('partner_id', '=', partner.id),
                ('state', '=', 'paused'),
                ('pause_reason', '=', 'majority_pending'),
            ])
            if schedules:
                schedules._resume_from_majority_pending()
                body = _(
                    "Consentement personnel confirmé par %(user)s le %(date)s "
                    "— représentant légal remplacé, calendrier réactivé.",
                    user=self.env.user.name,
                    date=fields.Date.to_string(fields.Date.today()),
                )
                partner.message_post(body=body)
                for schedule in schedules:
                    try:
                        schedule.sudo().message_post(
                            body=body, subtype_xmlid='mail.mt_note',
                        )
                    except Exception as exc:  # noqa: BLE001 — chatter non critique
                        _logger.exception(
                            "Confirm majority — chatter schedule %s ignoré (%s).",
                            schedule.id, exc,
                        )
            else:
                # Pas de schedule à ré-ouvrir (partner sans schedule pending
                # ou tous schedules paused pour autre motif). Posté quand
                # même sur partner pour audit.
                partner.message_post(body=_(
                    "Consentement personnel confirmé par %(user)s — "
                    "représentant légal remplacé (aucun calendrier à réactiver).",
                    user=self.env.user.name,
                ))
        return True

    # ==================================================================
    # AC-B — Anonymisation cyclique (Story 17-3)
    # ==================================================================

    _ANONYMIZE_INACTIVITY_YEARS = 5
    _ANONYMIZE_OPTOUT_MONTHS = 12

    @api.model
    def _anonymize_get_candidates(self):
        """Retourne les partners éligibles à l'anonymisation cyclique.

        Critères (AC-B.1) :
          - ``optical_anonymized == False``
          - ``is_company == False``
          - OU inclusif :
            (a) ``optical_followup_optout_date + 12 mois <= today``
            (b) dernière ``sale.order`` (tous états sauf ``cancel``) date_order
                + 5 ans <= today
          - Un partner sans aucune SO n'est PAS éligible via (b).
        """
        today = fields.Date.today()
        threshold_optout = fields.Date.subtract(
            today, months=self._ANONYMIZE_OPTOUT_MONTHS,
        )
        threshold_inactive = fields.Date.subtract(
            today, years=self._ANONYMIZE_INACTIVITY_YEARS,
        )

        candidates = self.env['res.partner']

        # Piste (a) — opt-out > 12 mois
        candidates |= self.sudo().search([
            ('optical_anonymized', '=', False),
            ('is_company', '=', False),
            ('optical_followup_optout_date', '!=', False),
            ('optical_followup_optout_date', '<=', threshold_optout),
        ])

        # Piste (b) — inactifs > 5 ans (dernière SO non-cancel très ancienne)
        SO = self.env['sale.order'].sudo()
        # Partners ayant AU MOINS une SO non-cancel toutes ≤ threshold_inactive
        # → équivalent à : partner_id NOT IN (partners avec SO date > threshold)
        recent_partner_ids = SO.search([
            ('state', '!=', 'cancel'),
            ('date_order', '>', threshold_inactive),
        ]).mapped('partner_id').ids
        stale_partner_ids = SO.search([
            ('state', '!=', 'cancel'),
            ('date_order', '<=', threshold_inactive),
        ]).mapped('partner_id').ids
        stale_only = set(stale_partner_ids) - set(recent_partner_ids)
        if stale_only:
            candidates |= self.sudo().browse(list(stale_only)).filtered(
                lambda p: not p.optical_anonymized and not p.is_company
            )
        return candidates

    @api.model
    def _anonymize_dry_run(self):
        """Helper admin — retourne (count, records) sans effet de bord.

        À invoquer manuellement avant l'activation du cron mensuel :
        ``env['res.partner']._anonymize_dry_run()``.
        Log un compte-rendu en info.
        """
        candidates = self._anonymize_get_candidates()
        _logger.info(
            "Anonymisation dry-run — %d partner(s) éligibles : %s",
            len(candidates),
            candidates.mapped('name'),
        )
        return (len(candidates), candidates)

    def _anonymize_for_followup(self, reason='inactive_5y'):
        """Anonymise irréversiblement les partners self (AC-B.2).

        ``reason`` ∈ {``'optout_12m'``, ``'inactive_5y'``}.

        Effets par partner (une transaction chacun, appelant fournit le
        savepoint) :
          - PII effacées / réinitialisées (voir story AC-B.2 pour la liste)
          - ``name`` remplacé par ``"Client anonymisé #<id>"``
          - Champs consentement / opt-out / majority remis à False
          - ``optical_anonymized = True`` + ``optical_anonymized_date = today``
          - Schedules ``running`` OU ``paused`` cancelled + activités unlinked
          - Chatter final sur partner + audit trail comptable préservé
        """
        today = fields.Date.today()
        Schedule = self.env['optical.followup.schedule'].sudo()
        for partner in self:
            # Cascade schedules : cancel les running/paused, unlink activités.
            schedules = Schedule.search([
                ('partner_id', '=', partner.id),
                ('state', 'in', ('running', 'paused')),
            ])
            activities = self.env['mail.activity']
            for schedule in schedules:
                pending_lines = schedule.line_ids.filtered(
                    lambda l: l.state in ('pending', 'overdue', 'paused')
                )
                activities |= pending_lines.mapped('activity_id')
                pending_lines.write({'state': 'cancelled'})
            if activities:
                activities.sudo().unlink()
            if schedules:
                schedules.write({'state': 'cancelled'})

            # Wipe PII + poser flags anonymisation dans la même écriture.
            # Context flag évite le blocage write-once qu'on vient d'installer.
            partner.with_context(optical_anonymize_in_progress=True).sudo().write({
                'name': _("Client anonymisé #%d") % partner.id,
                'email': False,
                'phone': False,
                'mobile': False,
                'street': False,
                'street2': False,
                'city': False,
                'zip': False,
                'vat': False,
                'image_1920': False,
                'comment': False,
                'birthdate': False,
                'optical_followup_consent': False,
                'optical_followup_consent_date': False,
                'optical_followup_consent_by_id': False,
                'optical_followup_consent_by_legal_rep': False,
                'optical_followup_optout': False,
                'optical_followup_optout_date': False,
                'optical_followup_optout_reason': False,
                'optical_followup_majority_request_date': False,
                # Story 18-1 AC-3.4 — reset override tier (le compute retombera
                # naturellement sur le tier par défaut / CA cumulé, mais on
                # n'hérite pas d'un override manuel silencieux).
                'optical_customer_tier_override_id': False,
                'optical_anonymized': True,
                'optical_anonymized_date': today,
            })
            reason_label = {
                'optout_12m': _("opposition > 12 mois"),
                'inactive_5y': _("inactivité > 5 ans"),
            }.get(reason, reason)
            try:
                partner.sudo().message_post(body=_(
                    "Fiche client anonymisée le %(date)s (%(reason)s).",
                    date=fields.Date.to_string(today),
                    reason=reason_label,
                ))
            except Exception as exc:  # noqa: BLE001 — chatter non critique
                _logger.exception(
                    "Anonymisation — chatter final partner %s ignoré (%s).",
                    partner.id, exc,
                )
        return True

    @api.model
    def _run_monthly_anonymize(self):
        """Story 17-3 AC-B.1 — cron mensuel (livré ``active=False``).

        Résilience savepoint par partner. Log récapitulatif + chatter posté
        sur ``env.user.partner_id`` (l'admin ODOO du cron voit passer le
        récapitulatif sans consulter les logs serveur).
        """
        today = fields.Date.today()
        threshold_optout = fields.Date.subtract(
            today, months=self._ANONYMIZE_OPTOUT_MONTHS,
        )
        candidates = self._anonymize_get_candidates()
        if not candidates:
            _logger.info(
                "Anonymisation mensuelle : 0 partner éligible ce mois-ci.",
            )
            return 0

        n_success = 0
        n_fail = 0
        for partner in candidates:
            # Déterminer la raison — priorité opt-out (plus explicite légalement)
            if (
                partner.optical_followup_optout_date
                and partner.optical_followup_optout_date <= threshold_optout
            ):
                reason = 'optout_12m'
            else:
                reason = 'inactive_5y'
            try:
                with self.env.cr.savepoint():
                    partner._anonymize_for_followup(reason=reason)
                n_success += 1
            except Exception as exc:  # noqa: BLE001 — résilience cron
                _logger.exception(
                    "Anonymisation partner %s ignorée (%s).", partner.id, exc,
                )
                n_fail += 1

        _logger.info(
            "Anonymisation mensuelle : %d partners traités, %d succès, %d échecs.",
            len(candidates), n_success, n_fail,
        )
        try:
            self.env.user.partner_id.sudo().message_post(body=_(
                "Anonymisation cyclique — %(total)s partners traités "
                "(%(ok)s succès, %(ko)s échecs) le %(date)s.",
                total=len(candidates),
                ok=n_success,
                ko=n_fail,
                date=fields.Date.to_string(today),
            ))
        except Exception as exc:  # noqa: BLE001 — chatter non critique
            _logger.exception("Anonymisation — chatter admin ignoré (%s).", exc)
        return n_success

    # ==================================================================
    # AC-D — Extrait droit d'accès CDP (Story 17-3, FR-14)
    # ==================================================================

    def action_optical_followup_data_export(self):
        """Génère et attache au chatter un extrait des données personnelles.

        Story 17-3 AC-D — Loi 2008-12 art. 65-71 (droit d'accès CDP).

        Garde-fou Python groupe manager (défense en profondeur — la view
        expose `groups=` mais l'action pourrait être appelée depuis un
        script / wizard). Le garde-fou URL est porté par l'AbstractModel
        ``report.optical_crm_followup.report_partner_data_export_document``.

        Retour :
          - Personne physique : ``report.report_action`` (déclenche le PDF)
            + PDF attaché au chatter partner + trace user manager.
          - Personne morale : dict warning UI, aucune génération.
        """
        self.ensure_one()
        if not self.env.user.has_group('optical.group_optical_manager'):
            raise AccessError(_(
                "Seul un responsable peut générer un extrait droit d'accès."
            ))
        if self.is_company:
            return {
                'warning': {
                    'title': _("Non applicable"),
                    'message': _(
                        "Loi 2008-12 art. 65-71 s'applique aux personnes "
                        "physiques uniquement."
                    ),
                },
            }
        report_ref = 'optical_crm_followup.action_report_partner_data_export'
        report = self.env.ref(report_ref, raise_if_not_found=False)
        if not report:
            raise UserError(_(
                "Rapport droit d'accès introuvable (%s).", report_ref,
            ))
        # NOTE : pas de sudo() ici — le garde-fou AbstractModel doit voir le
        # vrai env.user (déjà validé manager par le check Python ci-dessus).
        pdf_content, _content_type = report._render_qweb_pdf(
            report_ref, [self.id],
        )
        filename = _("droit-acces-%(name)s-%(date)s.pdf",
                     name=(self.name or '').replace(' ', '_'),
                     date=fields.Date.to_string(fields.Date.today()))
        attachment = self.env['ir.attachment'].sudo().create({
            'name': filename,
            'datas': base64.b64encode(pdf_content) if pdf_content else False,
            'res_model': 'res.partner',
            'res_id': self.id,
            'type': 'binary',
            'mimetype': 'application/pdf',
        })
        self.sudo().message_post(
            body=_(
                "Extrait droit d'accès généré le %(date)s par %(user)s "
                "(audit CDP).",
                date=fields.Date.to_string(fields.Date.today()),
                user=self.env.user.name,
            ),
            attachment_ids=[attachment.id],
            subtype_xmlid='mail.mt_note',
        )
        try:
            self.env.user.partner_id.sudo().message_post(body=_(
                "Extrait droit d'accès généré pour %(partner)s.",
                partner=self.name or _("(sans nom)"),
            ))
        except Exception as exc:  # noqa: BLE001 — trace secondaire non critique
            _logger.exception(
                "Data export — trace user manager ignorée (%s).", exc,
            )
        return report.report_action(self)
