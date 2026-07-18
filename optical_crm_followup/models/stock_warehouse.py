# -*- coding: utf-8 -*-
"""Story 17-2 (revue M7) — Extension stock.warehouse pour reporting.

Ventilation par boutique du taux de désabonnement rapide 30 j (AC-4.4) —
le compute équivalent existe sur ``optical.followup.plan`` (ventilation par
preset). Cette extension complète la couverture AC-4.4 qui exige
« ventilation par preset ET par boutique ».
"""
from odoo import _, api, fields, models

_FAST_UNSUBSCRIBE_WINDOW_DAYS = 30


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    optical_fast_unsubscribe_rate_30d_display = fields.Char(
        string="Taux désabonnement 30 j (fidélisation)",
        compute='_compute_optical_fast_unsubscribe_rate_30d_display',
        store=False,
        help="Sous-métrique FR-23 (Story 17-2 AC-4.4) : proportion de "
             "clients ayant opt-out dans les 30 j suivant leur 1ʳᵉ relance, "
             "sur l'ensemble des clients ayant reçu une 1ʳᵉ relance dans la "
             "période, tous plans confondus pour cette boutique. Affiche "
             "'—' si aucun 1ᵉʳ contact sur la période.",
    )

    @api.depends('active')
    def _compute_optical_fast_unsubscribe_rate_30d_display(self):
        """Story 17-2 AC-4.4 (revue M7) — désabonnement rapide par boutique.

        Batch-safe : 1 seule ``search`` sur ``optical.followup.schedule``
        pour toutes les warehouses self, dispatch en Python.
        """
        if not self:
            return
        Schedule = self.env['optical.followup.schedule'].sudo()
        today = fields.Date.today()
        window_start = fields.Date.subtract(today, days=_FAST_UNSUBSCRIBE_WINDOW_DAYS)
        all_schedules = Schedule.search([
            ('warehouse_id', 'in', self.ids),
            ('first_contact_date', '!=', False),
            ('first_contact_date', '>=', window_start),
        ])
        by_wh = {}
        for schedule in all_schedules:
            by_wh.setdefault(schedule.warehouse_id.id, []).append(schedule)
        for warehouse in self:
            schedules = by_wh.get(warehouse.id, [])
            if not schedules:
                warehouse.optical_fast_unsubscribe_rate_30d_display = '—'
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
            warehouse.optical_fast_unsubscribe_rate_30d_display = "%.0f %%" % rate
