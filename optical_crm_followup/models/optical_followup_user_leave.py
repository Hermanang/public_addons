# -*- coding: utf-8 -*-
"""Story 17-3 AC-E — Redirection temporaire d'absence longue.

Modèle ``optical.followup.user.leave`` : représente une période d'absence
programmée d'un commercial (congé maternité, sabbatique, arrêt long, etc.)
avec redirection automatique des activités pendantes vers un suppléant
désigné manuellement par le responsable.

Cycle de vie :

    planned ────► active ────► ended
        │            │
        │            └─ ré-réattribution des activités au titulaire
        │               (cron ``_run_daily_rh_cron`` @ 06 h 00)
        │
        └─ réassignation des activités pendantes vers substitute
           (cron ``_run_daily_rh_cron`` OU bouton manuel)

L'idempotence est garantie côté cron (no-op si state incorrect) et côté
matérialisation d'activité (hook ``_get_effective_followup_user`` interrogé
par ``_materialize_step_activity`` — aller-simple, pas d'aller-retour).
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class OpticalFollowupUserLeave(models.Model):
    _name = 'optical.followup.user.leave'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Absence temporaire d'un référent commercial (redirection fidélisation)"
    _order = 'date_start desc, id desc'

    name = fields.Char(
        string="Libellé",
        required=True,
        default="Nouvelle absence",
        help="Libellé libre (auto-généré si vide au démarrage).",
    )
    user_id = fields.Many2one(
        'res.users',
        string="Titulaire",
        required=True,
        ondelete='restrict',
        domain="[('active', '=', True)]",
        help="Commercial dont les activités seront redirigées pendant l'absence.",
    )
    substitute_user_id = fields.Many2one(
        'res.users',
        string="Suppléant",
        required=True,
        ondelete='restrict',
        domain="[('active', '=', True)]",
        help="Commercial recevant les activités pendant l'absence. "
             "Peut appartenir à une autre boutique (D-COMPLIANCE-LEAVE-SUBST-DIFF-WAREHOUSE = A).",
    )
    date_start = fields.Date(
        string="Date de début",
        required=True,
    )
    date_end = fields.Date(
        string="Date de fin",
        required=True,
    )
    state = fields.Selection(
        [
            ('planned', "Planifiée"),
            ('active', "En cours"),
            ('ended', "Terminée"),
        ],
        string="État",
        default='planned',
        required=True,
        readonly=True,
        help="Géré automatiquement par le cron RH quotidien (06 h 00) OU "
             "manuellement via le bouton d'activation.",
    )
    reason = fields.Char(
        string="Motif",
        help="Congé maternité, sabbatique, arrêt maladie, formation, etc. "
             "Utilisé dans le chatter partner (transparence commerciale).",
    )

    _sql_constraints = [
        (
            'date_end_after_start',
            'CHECK (date_end > date_start)',
            "La date de fin doit être postérieure à la date de début.",
        ),
    ]

    @api.constrains('user_id', 'substitute_user_id')
    def _check_substitute_differs(self):
        for leave in self:
            if leave.user_id == leave.substitute_user_id:
                raise ValidationError(_(
                    "Le suppléant doit être différent du titulaire."
                ))

    @api.constrains('user_id', 'date_start', 'date_end', 'state')
    def _check_no_overlap(self):
        for leave in self:
            if leave.state == 'ended':
                continue
            overlap = self.sudo().search([
                ('id', '!=', leave.id),
                ('user_id', '=', leave.user_id.id),
                ('state', '!=', 'ended'),
                ('date_start', '<=', leave.date_end),
                ('date_end', '>=', leave.date_start),
            ], limit=1)
            if overlap:
                raise ValidationError(_(
                    "Une absence non terminée existe déjà pour ce titulaire "
                    "sur cette période (%(other)s).",
                    other=overlap.name,
                ))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == 'Nouvelle absence':
                user = self.env['res.users'].browse(vals.get('user_id'))
                vals['name'] = _(
                    "Absence %(user)s %(start)s → %(end)s",
                    user=user.name or _('(sans titulaire)'),
                    start=vals.get('date_start', '?'),
                    end=vals.get('date_end', '?'),
                )
        return super().create(vals_list)

    def unlink(self):
        active_leaves = self.filtered(lambda l: l.state == 'active')
        if active_leaves:
            raise UserError(_(
                "Impossible de supprimer une absence en cours. "
                "Utilisez « Terminer maintenant » ou attendez la bascule automatique."
            ))
        return super().unlink()

    # ==================================================================
    # Actions manuelles (bouton form)
    # ==================================================================

    def action_optical_followup_leave_activate(self):
        """Bascule manuelle ``planned → active`` (arrêt maladie imprévu).

        Effet identique au cron : réassignation des activités pendantes
        vers substitute + chatter partner + chatter leave.
        """
        for leave in self:
            if leave.state != 'planned':
                raise UserError(_(
                    "Seule une absence planifiée peut être activée manuellement."
                ))
            leave._activate_and_reassign()
        return True

    def action_optical_followup_leave_end_now(self):
        """Bascule manuelle ``active → ended`` (retour anticipé)."""
        for leave in self:
            if leave.state != 'active':
                raise UserError(_(
                    "Seule une absence en cours peut être terminée."
                ))
            leave._end_and_revert()
        return True

    # ==================================================================
    # Bascules internes (pattern identique cron / manuel)
    # ==================================================================

    def _activate_and_reassign(self):
        """Passe la leave en ``active`` + réassigne les activités.

        Résilience : chaque partner impacté est isolé en savepoint.
        Chatter partner dédupliqué (1 message par partner impacté).
        """
        self.ensure_one()
        activities = self.env['mail.activity'].sudo().search([
            ('user_id', '=', self.user_id.id),
        ])
        # Filtrer aux activités du dispositif fidélisation
        Schedule = self.env['optical.followup.schedule'].sudo()
        followup_partner_ids = Schedule.search([
            ('referent_user_id', '=', self.user_id.id),
        ]).mapped('partner_id').ids
        activities = activities.filtered(
            lambda a: (
                a.res_model == 'optical.followup.schedule.line'
                or (a.res_model == 'res.partner' and a.res_id in followup_partner_ids)
            )
        )
        partners_impacted = set()
        for activity in activities:
            try:
                with self.env.cr.savepoint():
                    activity.sudo().write({'user_id': self.substitute_user_id.id})
                    if activity.res_model == 'res.partner':
                        partners_impacted.add(activity.res_id)
                    elif activity.res_model == 'optical.followup.schedule.line':
                        line = self.env['optical.followup.schedule.line'].sudo().browse(activity.res_id)
                        if line.exists() and line.schedule_id.partner_id:
                            partners_impacted.add(line.schedule_id.partner_id.id)
            except Exception as exc:  # noqa: BLE001 — résilience
                _logger.exception(
                    "Leave %s — reassign activity %s ignorée (%s).",
                    self.id, activity.id, exc,
                )
        self.write({'state': 'active'})
        # Chatter partner dédupliqué HORS savepoint
        Partner = self.env['res.partner']
        for partner_id in partners_impacted:
            partner = Partner.browse(partner_id).exists()
            if not partner:
                continue
            try:
                partner.sudo().message_post(body=_(
                    "Référent temporairement remplacé : %(user)s (%(reason)s) → "
                    "%(substitute)s jusqu'au %(date_end)s.",
                    user=self.user_id.name,
                    reason=self.reason or _("absence programmée"),
                    substitute=self.substitute_user_id.name,
                    date_end=fields.Date.to_string(self.date_end),
                ), subtype_xmlid='mail.mt_note')
            except Exception as exc:  # noqa: BLE001 — chatter non critique
                _logger.exception(
                    "Leave %s — chatter partner %s ignoré (%s).",
                    self.id, partner_id, exc,
                )
        try:
            self.sudo().message_post(body=_(
                "Absence activée — %(n)s activité(s) redirigée(s) vers %(sub)s.",
                n=len(activities),
                sub=self.substitute_user_id.name,
            ))
        except Exception as exc:  # noqa: BLE001 — chatter non critique
            _logger.exception(
                "Leave %s — chatter leave activation ignoré (%s).", self.id, exc,
            )
        return len(activities)

    def _end_and_revert(self):
        """Passe la leave en ``ended`` + ré-réattribue les activités au titulaire.

        Filtre restrictif : ne re-touche que les activités du suppléant
        dont le partner a un ``schedule.referent_user_id == self.user_id``
        (les activités propres au suppléant sont préservées).

        Batch-fetch des schedule.lines pour éviter le pattern N+2
        (`browse().exists()` puis `.schedule_id` par activité — revue M5).
        """
        self.ensure_one()
        Schedule = self.env['optical.followup.schedule'].sudo()
        Line = self.env['optical.followup.schedule.line'].sudo()
        titular_partner_ids = Schedule.search([
            ('referent_user_id', '=', self.user_id.id),
        ]).mapped('partner_id').ids

        all_sub_activities = self.env['mail.activity'].sudo().search([
            ('user_id', '=', self.substitute_user_id.id),
        ])
        # Pré-charger en un seul browse les lignes candidates
        line_res_ids = [
            a.res_id for a in all_sub_activities
            if a.res_model == 'optical.followup.schedule.line'
        ]
        line_by_id = {}
        if line_res_ids:
            for line in Line.browse(line_res_ids).exists():
                line_by_id[line.id] = line

        def _keep_activity(activity):
            if activity.res_model == 'res.partner':
                return activity.res_id in titular_partner_ids
            if activity.res_model == 'optical.followup.schedule.line':
                line = line_by_id.get(activity.res_id)
                return bool(
                    line and line.schedule_id.referent_user_id.id == self.user_id.id
                )
            return False

        activities = all_sub_activities.filtered(_keep_activity)
        partners_impacted = set()
        for activity in activities:
            try:
                with self.env.cr.savepoint():
                    activity.sudo().write({'user_id': self.user_id.id})
                    if activity.res_model == 'res.partner':
                        partners_impacted.add(activity.res_id)
                    elif activity.res_model == 'optical.followup.schedule.line':
                        line = line_by_id.get(activity.res_id)
                        if line and line.schedule_id.partner_id:
                            partners_impacted.add(line.schedule_id.partner_id.id)
            except Exception as exc:  # noqa: BLE001 — résilience
                _logger.exception(
                    "Leave %s — revert activity %s ignorée (%s).",
                    self.id, activity.id, exc,
                )
        self.write({'state': 'ended'})
        Partner = self.env['res.partner']
        for partner_id in partners_impacted:
            partner = Partner.browse(partner_id).exists()
            if not partner:
                continue
            try:
                partner.sudo().message_post(body=_(
                    "Référent commercial de retour : activités re-basculées de "
                    "%(substitute)s vers %(user)s.",
                    substitute=self.substitute_user_id.name,
                    user=self.user_id.name,
                ), subtype_xmlid='mail.mt_note')
            except Exception as exc:  # noqa: BLE001 — chatter non critique
                _logger.exception(
                    "Leave %s — chatter partner %s ignoré (%s).",
                    self.id, partner_id, exc,
                )
        try:
            self.sudo().message_post(body=_(
                "Absence terminée — %(n)s activité(s) re-redirigée(s) vers %(user)s.",
                n=len(activities),
                user=self.user_id.name,
            ))
        except Exception as exc:  # noqa: BLE001 — chatter non critique
            _logger.exception(
                "Leave %s — chatter leave end ignoré (%s).", self.id, exc,
            )
        return len(activities)
