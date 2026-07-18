# -*- coding: utf-8 -*-
"""Story 17-3 AC-F — Wizard de réattribution en masse d'un portefeuille.

Utilisé par un ``optical.group_optical_manager`` pour redispatcher les
activités et/ou schedules d'un commercial source vers un cible. Trois
scopes : ``activities_only``, ``partners_referent``, ``both``. Un filtre
optionnel par warehouse restreint la portée géographique.

Preview computed en temps réel (N activités, M partners) — permet au
manager de vérifier l'impact avant validation. Transaction atomique.
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class OpticalFollowupReassignWizard(models.TransientModel):
    _name = 'optical.followup.reassign.wizard'
    _description = "Wizard de réattribution en masse d'un portefeuille commercial"

    source_user_id = fields.Many2one(
        'res.users',
        string="Commercial source",
        required=True,
        help="Commercial dont les activités et/ou schedules seront redispatchés.",
    )
    target_user_id = fields.Many2one(
        'res.users',
        string="Commercial cible",
        required=True,
        help="Commercial recevant les activités et/ou schedules.",
    )
    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        'optical_followup_reassign_wizard_warehouse_rel',
        'wizard_id',
        'warehouse_id',
        string="Boutiques (filtre)",
        help="Si renseigné, la réattribution se limite aux partners liés à "
             "ces boutiques (via schedule.warehouse_id). Sinon toutes boutiques.",
    )
    transfer_scope = fields.Selection(
        [
            ('activities_only', "Activités pendantes uniquement"),
            ('partners_referent', "Référent des schedules uniquement"),
            ('both', "Les deux"),
        ],
        string="Portée",
        default='both',
        required=True,
    )
    reason = fields.Char(
        string="Raison (obligatoire, min. 5 caractères)",
        required=True,
        help="Motif de la réattribution — inscrit dans le chatter partner "
             "et users pour traçabilité (audit RH / continuité).",
    )
    preview_activities_count = fields.Integer(
        string="Activités concernées",
        compute='_compute_preview_counts',
        store=False,
    )
    preview_partners_count = fields.Integer(
        string="Partners concernés",
        compute='_compute_preview_counts',
        store=False,
    )

    @api.constrains('source_user_id', 'target_user_id')
    def _check_source_not_target(self):
        for wizard in self:
            if wizard.source_user_id == wizard.target_user_id:
                raise ValidationError(_(
                    "Impossible de réattribuer un portefeuille vers son propre "
                    "référent."
                ))

    @api.constrains('reason')
    def _check_reason_length(self):
        for wizard in self:
            if not wizard.reason or len(wizard.reason.strip()) < 5:
                raise ValidationError(_(
                    "La raison de la réattribution doit contenir au moins 5 "
                    "caractères (traçabilité RH)."
                ))

    def _check_manager_or_raise(self):
        if not self.env.user.has_group('optical.group_optical_manager'):
            raise AccessError(_(
                "Seul un responsable peut réattribuer un portefeuille commercial."
            ))

    @api.depends('source_user_id', 'target_user_id', 'warehouse_ids', 'transfer_scope')
    def _compute_preview_counts(self):
        for wizard in self:
            if not wizard.source_user_id:
                wizard.preview_activities_count = 0
                wizard.preview_partners_count = 0
                continue
            activities, schedules, partners = wizard._resolve_targets()
            wizard.preview_activities_count = len(activities)
            wizard.preview_partners_count = len(partners)

    def _resolve_targets(self):
        """Retourne le triplet (activities, schedules, partners_impacted).

        - activities : ``mail.activity`` du dispositif où user_id=source
        - schedules : running/paused avec referent_user_id=source
        - partners : union unique des partners impactés
        """
        self.ensure_one()
        Schedule = self.env['optical.followup.schedule'].sudo()
        Activity = self.env['mail.activity'].sudo()

        schedule_domain = [
            ('referent_user_id', '=', self.source_user_id.id),
            ('state', 'in', ('running', 'paused')),
        ]
        if self.warehouse_ids:
            schedule_domain.append(('warehouse_id', 'in', self.warehouse_ids.ids))
        schedules = Schedule.search(schedule_domain)
        partner_ids = set(schedules.mapped('partner_id').ids)

        activities = Activity.browse()
        if self.transfer_scope in ('activities_only', 'both'):
            all_activities = Activity.search([
                ('user_id', '=', self.source_user_id.id),
            ])
            activities = all_activities.filtered(
                lambda a: (
                    a.res_model == 'optical.followup.schedule.line'
                    or (a.res_model == 'res.partner' and a.res_id in partner_ids)
                )
            )
            # Enrichir la liste partners avec ceux issus des activités
            for activity in activities:
                if activity.res_model == 'res.partner':
                    partner_ids.add(activity.res_id)
                elif activity.res_model == 'optical.followup.schedule.line':
                    line = self.env['optical.followup.schedule.line'].sudo().browse(activity.res_id).exists()
                    if line and line.schedule_id.partner_id:
                        partner_ids.add(line.schedule_id.partner_id.id)

        # Filtrer les schedules selon scope
        if self.transfer_scope == 'activities_only':
            schedules_out = Schedule.browse()
        else:
            schedules_out = schedules

        partners = self.env['res.partner'].sudo().browse(list(partner_ids)).exists()
        return activities, schedules_out, partners

    def action_confirm(self):
        """Story 17-3 AC-F.2 — validation transactionnelle.

        Batch write sur activités et/ou schedules + chatters dédupliqués +
        pose de ``previous_referent_user_id`` (conditional).
        """
        self._check_manager_or_raise()
        self.ensure_one()

        activities, schedules, partners = self._resolve_targets()

        # Garde-fou UX : scope partners_referent avec 0 schedule → erreur
        if self.transfer_scope == 'partners_referent' and not schedules:
            raise UserError(_(
                "Aucun schedule actif ou suspendu pour ce référent. "
                "Choisissez un autre scope ou vérifiez la source."
            ))
        if not activities and not schedules:
            raise UserError(_(
                "Aucune activité ni schedule à réattribuer pour la sélection."
            ))

        n_activities = 0
        n_schedules = 0

        if self.transfer_scope in ('activities_only', 'both') and activities:
            activities.write({'user_id': self.target_user_id.id})
            n_activities = len(activities)

        if self.transfer_scope in ('partners_referent', 'both') and schedules:
            schedules.write({'referent_user_id': self.target_user_id.id})
            n_schedules = len(schedules)

        # Pose conditionnelle du previous_referent — un partner par un
        # (write conditionnel : ne pas écraser une trace différente)
        for partner in partners:
            if partner.optical_followup_previous_referent_user_id != self.source_user_id:
                partner.sudo().write({
                    'optical_followup_previous_referent_user_id': self.source_user_id.id,
                })

        # Chatter partner dédupliqué (1 msg par partner)
        for partner in partners:
            try:
                partner.sudo().message_post(body=_(
                    "Portefeuille réattribué de %(src)s à %(tgt)s par "
                    "%(manager)s. Raison : %(reason)s.",
                    src=self.source_user_id.name,
                    tgt=self.target_user_id.name,
                    manager=self.env.user.name,
                    reason=self.reason,
                ), subtype_xmlid='mail.mt_note')
            except Exception as exc:  # noqa: BLE001 — chatter non critique
                _logger.exception(
                    "Réattribution wizard — chatter partner %s ignoré (%s).",
                    partner.id, exc,
                )

        # Chatter source + target users
        try:
            self.source_user_id.partner_id.sudo().message_post(body=_(
                "%(n_act)s activité(s) et %(n_part)s partner(s) réattribué(s) "
                "vers %(tgt)s par %(manager)s. Raison : %(reason)s.",
                n_act=n_activities,
                n_part=len(partners),
                tgt=self.target_user_id.name,
                manager=self.env.user.name,
                reason=self.reason,
            ))
        except Exception as exc:  # noqa: BLE001 — chatter non critique
            _logger.exception(
                "Réattribution wizard — chatter source ignoré (%s).", exc,
            )
        try:
            self.target_user_id.partner_id.sudo().message_post(body=_(
                "%(n_act)s activité(s) et %(n_part)s partner(s) reçu(s) de "
                "%(src)s par %(manager)s. Raison : %(reason)s.",
                n_act=n_activities,
                n_part=len(partners),
                src=self.source_user_id.name,
                manager=self.env.user.name,
                reason=self.reason,
            ))
        except Exception as exc:  # noqa: BLE001 — chatter non critique
            _logger.exception(
                "Réattribution wizard — chatter target ignoré (%s).", exc,
            )

        if not self.source_user_id.active:
            _logger.info(
                "Réattribution wizard : source user %s inactif (post-mortem OK).",
                self.source_user_id.login,
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Réattribution effectuée"),
                'message': _(
                    "%(n_act)s activité(s) et %(n_part)s partner(s) réattribué(s).",
                    n_act=n_activities,
                    n_part=len(partners),
                ),
                'type': 'success',
                'sticky': False,
            },
        }
