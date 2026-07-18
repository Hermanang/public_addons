# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    optical_warehouse_ids = fields.Many2many(
        'stock.warehouse',
        'optical_crm_followup_res_users_warehouse_rel',
        'user_id',
        'warehouse_id',
        string="Boutiques de fidélisation",
        help=(
            "Boutiques auxquelles ce commercial est rattaché pour le dispositif "
            "de fidélisation. Filtre les calendriers de suivi visibles dans les "
            "vues quotidiennes. Les responsables (group_optical_manager) voient "
            "tous les calendriers indépendamment de ce champ."
        ),
    )

    # ==================================================================
    # Story 17-3 AC-E.3 — Helper suppléance leave active
    # ==================================================================

    @api.model
    def _get_effective_followup_user(self, user):
        """Retourne le user à qui assigner effectivement une activité.

        Si ``user`` a un ``optical.followup.user.leave`` en ``state='active'``,
        retourne le suppléant — permet une assignation « aller-simple »
        (pas de create-then-update) lors de la matérialisation cron 00 h 30.

        Sinon retourne ``user`` inchangé.
        """
        if not user or not user.active:
            return user
        Leave = self.env['optical.followup.user.leave'].sudo()
        leave = Leave.search([
            ('user_id', '=', user.id),
            ('state', '=', 'active'),
        ], limit=1)
        if leave:
            return leave.substitute_user_id or user
        return user

    # ==================================================================
    # Story 17-3 AC-C — Override write (continuité départ commercial)
    # ==================================================================

    def write(self, vals):
        # Snapshot AVANT super() : pour chaque user en cours de désactivation,
        # capturer les partners + activités liés au dispositif fidélisation.
        # Pattern helpdesk.ticket.write S16.2 (accord AC7 rétro 16).
        snapshot = {}
        deactivating = 'active' in vals and not vals.get('active')
        if deactivating:
            for user in self:
                if not user.active:
                    continue  # déjà inactif → idempotence AC-C.3
                schedules = self.env['optical.followup.schedule'].sudo().search([
                    ('referent_user_id', '=', user.id),
                    ('state', 'in', ('running', 'paused')),
                ])
                partner_ids = schedules.mapped('partner_id').ids
                activities = self.env['mail.activity'].sudo().search([
                    ('user_id', '=', user.id),
                ]).filtered(
                    lambda a: (
                        a.res_model == 'optical.followup.schedule.line'
                        or (a.res_model == 'res.partner' and a.res_id in partner_ids)
                    )
                )
                snapshot[user.id] = {
                    'partner_ids': partner_ids,
                    'activity_ids': activities.ids,
                    'schedule_ids': schedules.ids,
                }

        result = super().write(vals)

        # Post-super : pour chaque user devenu inactif, déclencher le pivot.
        # La désactivation user ne rollback JAMAIS sur exception du pivot
        # (l'admin ne doit pas voir sa désactivation échouer à cause du
        # side-effect fidélisation — AC-C.3).
        if deactivating:
            for user in self:
                if user.id not in snapshot:
                    continue
                if user.active:
                    # Le vals contient active=False mais l'ORM n'a pas
                    # appliqué la bascule (edge : write bypass, unlikely) — skip
                    continue
                try:
                    self.env['optical.followup.schedule']._sync_referent_change_for_user(
                        user, snapshot[user.id],
                    )
                except Exception as exc:  # noqa: BLE001 — résilience globale
                    _logger.exception(
                        "Sync référent user %s post-désactivation ignorée (%s).",
                        user.id, exc,
                    )
        return result
