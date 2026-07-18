# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install', 'optical_crm_followup')
class TestS02HolidayWindows(TransactionCase):
    """Story 16.1 — Preset Progressifs 24m et fenêtres de vigilance."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.group_optical_user = cls.env.ref('optical.group_optical_user')
        cls.group_optical_manager = cls.env.ref('optical.group_optical_manager')

        base_group = cls.env.ref('base.group_user').id
        partner_manager = cls.env.ref('base.group_partner_manager').id
        stock_manager = cls.env.ref('stock.group_stock_manager').id
        sales_manager = cls.env.ref('sales_team.group_sale_manager').id
        group_all_ou = cls.env.ref(
            'operating_unit_access_all.group_all_operating_unit',
            raise_if_not_found=False,
        )
        cls.base_groups = [base_group, partner_manager, stock_manager, sales_manager]
        if group_all_ou:
            cls.base_groups.append(group_all_ou.id)

        cls.warehouse = cls.env['stock.warehouse'].create({
            'name': 'Boutique S16.1',
            'code': 'S161',
        })

        cls.user_referent = cls.env['res.users'].with_context(
            no_reset_password=True
        ).create({
            'name': 'Commercial S16.1',
            'login': 'commercial_s161',
            'email': 'commercial_s161@test.com',
            'groups_id': [Command.set([cls.group_optical_user.id] + cls.base_groups)],
            'optical_warehouse_ids': [Command.set([cls.warehouse.id])],
        })

        cls.partner_adult = cls.env['res.partner'].create({
            'name': 'Client Adulte S16.1',
            'birthdate': date.today() - timedelta(days=int(30 * 365.25)),
            'email': 'adult_s161@test.com',
        })
        cls.partner_adult.write({'optical_followup_consent': True})

        # Produits — unifocal / progressive / lentille
        cls.product_unifocal = cls.env['product.product'].create({
            'name': 'Verre Unifocal S16.1',
            'type': 'consu',
            'list_price': 100.0,
        })
        cls.product_unifocal.product_tmpl_id.write({
            'optical_type': 'lens',
            'lens_design': 'single_vision',
        })
        cls.product_progressive = cls.env['product.product'].create({
            'name': 'Verre Progressif S16.1',
            'type': 'consu',
            'list_price': 200.0,
        })
        cls.product_progressive.product_tmpl_id.write({
            'optical_type': 'lens',
            'lens_design': 'progressive',
        })

        # Références plans
        cls.plan_std18m = cls.env.ref('optical_crm_followup.plan_standard_18m')
        cls.plan_progressive = cls.env.ref(
            'optical_crm_followup.plan_progressive_24m'
        )

        # Fenêtres livrées
        cls.win_ramadan = cls.env.ref('optical_crm_followup.holiday_window_ramadan')
        cls.win_aid_fitr = cls.env.ref('optical_crm_followup.holiday_window_aid_fitr')
        cls.win_tabaski = cls.env.ref('optical_crm_followup.holiday_window_tabaski')
        cls.win_magal = cls.env.ref('optical_crm_followup.holiday_window_magal')
        cls.win_fin_annee = cls.env.ref(
            'optical_crm_followup.holiday_window_fin_annee'
        )
        cls.win_rentree = cls.env.ref('optical_crm_followup.holiday_window_rentree')

        # Lunaires 2026
        cls.lunar_ramadan_2026 = cls.env.ref(
            'optical_crm_followup.lunar_date_ramadan_2026'
        )
        cls.lunar_aid_adha_2026 = cls.env.ref(
            'optical_crm_followup.lunar_date_aid_adha_2026'
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_sale_order(self, partner, products=None):
        products = products or [self.product_unifocal]
        vals = {
            'partner_id': partner.id,
            'user_id': self.user_referent.id,
            'order_line': [
                Command.create({'product_id': p.id, 'product_uom_qty': 1})
                for p in products
            ],
        }
        return self.env['sale.order'].create(vals)

    def _confirm_and_deliver(self, so):
        so.action_confirm()
        pickings = so.picking_ids.filtered(
            lambda p: p.picking_type_id.code == 'outgoing'
        )
        for picking in pickings:
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
            picking.button_validate()
        return pickings

    def _create_schedule_direct(self, plan, partner, delivered_date=None):
        delivered_date = delivered_date or fields.Date.today()
        schedule = self.env['optical.followup.schedule'].create({
            'name': 'SCH-S161-%s' % partner.id,
            'partner_id': partner.id,
            'warehouse_id': self.warehouse.id,
            'plan_id': plan.id,
            'referent_user_id': self.user_referent.id,
            'delivered_date': delivered_date,
            'state': 'running',
        })
        for step in plan.step_ids:
            self.env['optical.followup.schedule.line'].create({
                'schedule_id': schedule.id,
                'step_id': step.id,
                'sequence': step.sequence,
                'date_planned': fields.Date.add(delivered_date, days=step.offset_days),
                'date_planned_original': fields.Date.add(delivered_date, days=step.offset_days),
                'state': 'pending',
            })
        return schedule

    # ==================================================================
    # AC1 — Preset Progressifs 24m appliqué automatiquement
    # ==================================================================

    def test_hook_creates_progressive_schedule_when_progressive_product_in_so(self):
        """AC1 — SO avec produit progressif → schedule plan_progressive_24m + 13 lignes."""
        so = self._make_sale_order(self.partner_adult, [self.product_progressive])
        self._confirm_and_deliver(so)

        schedule = self.env['optical.followup.schedule'].search([
            ('partner_id', '=', self.partner_adult.id),
            ('state', '=', 'running'),
        ])
        self.assertEqual(len(schedule), 1)
        self.assertEqual(schedule.plan_id, self.plan_progressive)
        self.assertEqual(len(schedule.line_ids), 13)
        self.assertTrue(all(l.state == 'pending' for l in schedule.line_ids))

    def test_progressive_schedule_has_13_lines_at_expected_offsets(self):
        """AC1 — 13 lignes avec offsets attendus : 0, 3, 7, 15, 30, 90, 180, 270,
        365, 455, 547, 637, 730."""
        so = self._make_sale_order(self.partner_adult, [self.product_progressive])
        self._confirm_and_deliver(so)
        schedule = so.followup_schedule_id
        expected_offsets = [0, 3, 7, 15, 30, 90, 180, 270, 365, 455, 547, 637, 730]
        actual_offsets = sorted(schedule.line_ids.mapped('step_id.offset_days'))
        self.assertEqual(actual_offsets, expected_offsets)
        for line in schedule.line_ids:
            expected_date = fields.Date.add(
                schedule.delivered_date, days=line.step_id.offset_days,
            )
            self.assertEqual(line.date_planned, expected_date)
            self.assertEqual(line.date_planned_original, expected_date)

    def test_progressive_priority_over_unifocal(self):
        """AC1 — SO mixte progressive + unifocal → plan_progressive_24m retenu."""
        so = self._make_sale_order(
            self.partner_adult,
            [self.product_progressive, self.product_unifocal],
        )
        self._confirm_and_deliver(so)
        schedule = so.followup_schedule_id
        self.assertEqual(schedule.plan_id, self.plan_progressive)

    def test_progressive_falls_back_to_std18m_if_plan_deactivated(self):
        """AC1 — plan progressive désactivé → fallback plan Std 18m."""
        self.plan_progressive.write({'active': False})
        try:
            so = self._make_sale_order(
                self.partner_adult, [self.product_progressive],
            )
            self._confirm_and_deliver(so)
            schedule = so.followup_schedule_id
            self.assertEqual(schedule.plan_id, self.plan_std18m)
        finally:
            self.plan_progressive.write({'active': True})

    # ==================================================================
    # AC2 — Preset FR-12 modifiable post-install
    # ==================================================================

    def test_progressive_preset_editable_post_install(self):
        """AC2 — modifier offset_days d'un step est reflété par les nouveaux schedules."""
        step_j7 = self.env.ref(
            'optical_crm_followup.plan_progressive_24m_step_j7'
        )
        original = step_j7.offset_days
        try:
            step_j7.write({'offset_days': 10})
            so = self._make_sale_order(
                self.partner_adult, [self.product_progressive],
            )
            self._confirm_and_deliver(so)
            schedule = so.followup_schedule_id
            line = schedule.line_ids.filtered(lambda l: l.step_id == step_j7)
            self.assertEqual(len(line), 1)
            self.assertEqual(
                line.date_planned,
                fields.Date.add(schedule.delivered_date, days=10),
            )
        finally:
            step_j7.write({'offset_days': original})

    # ==================================================================
    # AC3, AC4 — Modèles fenêtres et lunaires chargés
    # ==================================================================

    def test_holiday_window_data_loaded(self):
        """AC3 — les 6 fenêtres livrées sont bien créées avec bons behavior."""
        expected = {
            self.win_ramadan: 'switch_channel_soft',
            self.win_aid_fitr: 'postpone_to_end',
            self.win_tabaski: 'postpone_to_end',
            self.win_magal: 'postpone_to_end',
            self.win_fin_annee: 'switch_channel_soft',
            self.win_rentree: 'none',
        }
        for window, expected_behavior in expected.items():
            self.assertTrue(window)
            self.assertTrue(window.active)
            self.assertEqual(window.behavior, expected_behavior)

    def test_lunar_date_data_loaded_2026_2030(self):
        """AC4 — 20 records lunaires : 4 événements × 5 années."""
        Lunar = self.env['optical.followup.lunar.date']
        events = ('ramadan_start', 'aid_fitr', 'aid_adha', 'magal')
        years = (2026, 2027, 2028, 2029, 2030)
        for year in years:
            for event in events:
                records = Lunar.search([
                    ('year', '=', year), ('event', '=', event),
                ])
                self.assertEqual(
                    len(records), 1,
                    "Lunaire %s %s doit exister en 1 exemplaire" % (event, year),
                )
                self.assertTrue(records.date_gregorian_start)
                self.assertTrue(records.verified)

    def test_lunar_date_unique_constraint(self):
        """AC4 — contrainte unique(year, event) empêche les doublons."""
        Lunar = self.env['optical.followup.lunar.date']
        # Utiliser un savepoint dédié + mute_logger pour éviter le rollback global.
        from psycopg2 import IntegrityError
        with self.assertRaises(IntegrityError):
            with mute_logger('odoo.sql_db'), self.env.cr.savepoint():
                Lunar.create({
                    'name': 'Doublon Ramadan 2026',
                    'year': 2026,
                    'event': 'ramadan_start',
                    'date_gregorian_start': date(2026, 2, 18),
                })

    def test_holiday_window_civil_dates_regex_validation(self):
        """AC3 — date civile hors format MM-DD → ValidationError."""
        Window = self.env['optical.followup.holiday.window']
        with self.assertRaises(ValidationError):
            Window.create({
                'name': 'Test invalide',
                'behavior': 'none',
                'date_start_civil': 'xx-xx',
                'date_end_civil': '01-03',
            })

    def test_holiday_window_civil_dates_invalid_month_day(self):
        """Revue S16.1 M2 — date civile avec mois/jour hors bornes → ValidationError."""
        Window = self.env['optical.followup.holiday.window']
        with self.assertRaises(ValidationError):
            Window.create({
                'name': 'Test mois invalide',
                'behavior': 'none',
                'date_start_civil': '13-01',  # mois 13 inexistant
                'date_end_civil': '01-03',
            })
        with self.assertRaises(ValidationError):
            Window.create({
                'name': 'Test jour invalide',
                'behavior': 'none',
                'date_start_civil': '02-31',  # 31 février inexistant
                'date_end_civil': '01-03',
            })

    # ==================================================================
    # AC5 — Résolution année-glissante
    # ==================================================================

    def test_get_effective_period_lunar_returns_gregorian_dates_from_table(self):
        """AC5 — fenêtre Ramadan + année 2026 → dates de la lunaire chargée."""
        start, end = self.win_ramadan._get_effective_period(2026)
        self.assertEqual(start, self.lunar_ramadan_2026.date_gregorian_start)
        self.assertEqual(end, self.lunar_ramadan_2026.date_gregorian_end)

    def test_get_effective_period_lunar_computes_end_from_duration_if_missing(self):
        """AC5 — vider date_gregorian_end → start + duration_days - 1."""
        self.lunar_ramadan_2026.write({'date_gregorian_end': False})
        try:
            start, end = self.win_ramadan._get_effective_period(2026)
            self.assertEqual(start, self.lunar_ramadan_2026.date_gregorian_start)
            self.assertEqual(
                end,
                fields.Date.add(start, days=self.win_ramadan.duration_days - 1),
            )
        finally:
            self.lunar_ramadan_2026.write({
                'date_gregorian_end': date(2026, 3, 19),
            })

    def test_get_effective_period_civil_handles_year_crossing(self):
        """AC5 — fenêtre 12-23 → 01-03 année 2026 → (2026-12-23, 2027-01-03)."""
        start, end = self.win_fin_annee._get_effective_period(2026)
        self.assertEqual(start, date(2026, 12, 23))
        self.assertEqual(end, date(2027, 1, 3))

    def test_get_effective_period_returns_false_if_lunar_missing_for_year(self):
        """AC5 — année non chargée → (False, False) + log warning."""
        with mute_logger('odoo.addons.optical_crm_followup.models.optical_followup_holiday_window'):
            start, end = self.win_ramadan._get_effective_period(2035)
        self.assertFalse(start)
        self.assertFalse(end)

    # ==================================================================
    # AC6 — Application postpone_to_end
    # ==================================================================

    def test_materialize_applies_postpone_to_end(self):
        """AC6 — ligne dans fenêtre postpone_to_end (Tabaski 2026) → report."""
        # date_planned = 2026-05-28 (milieu Tabaski 2026-05-27 → 2026-05-29)
        target_date = date(2026, 5, 28)
        schedule = self._create_schedule_direct(
            self.plan_std18m, self.partner_adult,
            delivered_date=target_date - timedelta(days=30),
        )
        line = schedule.line_ids.sorted('sequence')[0]
        line.write({'date_planned': target_date})
        line._materialize_step_activity()
        line.invalidate_recordset()

        self.assertEqual(line.holiday_window_id, self.win_tabaski)
        # Tabaski 2026 fin = 2026-05-29 → report à 2026-05-30
        self.assertEqual(line.date_planned, date(2026, 5, 30))
        self.assertEqual(line.date_planned_original, target_date)
        self.assertEqual(line.activity_id.date_deadline, date(2026, 5, 30))
        self.assertIn(
            'Reporté par fenêtre',
            line.activity_id.note or '',
        )
        # Chatter partner posté
        messages = self.partner_adult.message_ids.filtered(
            lambda m: 'reportée' in (m.body or '').lower()
        )
        self.assertTrue(messages, "Un message chatter doit avoir été posté sur le partner")

    # ==================================================================
    # AC7 — Application switch_channel_soft
    # ==================================================================

    def test_materialize_applies_switch_channel_soft(self):
        """AC7 — ligne dans fenêtre Ramadan (switch_channel_soft) → note enrichie,
        date_planned inchangé, aucun chatter partner."""
        target_date = date(2026, 3, 1)  # milieu Ramadan 2026
        schedule = self._create_schedule_direct(
            self.plan_std18m, self.partner_adult,
            delivered_date=target_date - timedelta(days=30),
        )
        line = schedule.line_ids.sorted('sequence')[0]  # step Appel (call)
        line.write({'date_planned': target_date})
        # Purger les messages existants pour vérifier l'absence
        n_msg_before = len(self.partner_adult.message_ids)
        line._materialize_step_activity()
        line.invalidate_recordset()

        self.assertEqual(line.holiday_window_id, self.win_ramadan)
        # date_planned inchangée
        self.assertEqual(line.date_planned, target_date)
        # Note enrichie
        note = line.activity_id.note or ''
        self.assertIn('Ramadan', note)
        self.assertIn('WhatsApp', note)
        # Aucun chatter posté (switch_channel_soft ne poste pas)
        self.partner_adult.invalidate_recordset()
        # Filtrer les messages hors création automatique
        new_msg = self.partner_adult.message_ids.filtered(
            lambda m: 'reportée' in (m.body or '').lower()
        )
        self.assertFalse(new_msg, "Aucun chatter 'reportée' ne doit être posté")

    # ==================================================================
    # AC8 — Comportement none (fenêtre neutre)
    # ==================================================================

    def test_materialize_behavior_none_is_no_op(self):
        """AC8 — ligne dans fenêtre Rentrée scolaire (none) → aucun impact."""
        target_date = date(2026, 9, 20)  # milieu rentrée scolaire
        schedule = self._create_schedule_direct(
            self.plan_std18m, self.partner_adult,
            delivered_date=target_date - timedelta(days=30),
        )
        line = schedule.line_ids.sorted('sequence')[0]
        line.write({'date_planned': target_date})
        line._materialize_step_activity()
        line.invalidate_recordset()

        # holiday_window_id vide (pas de traçabilité — behavior='none')
        self.assertFalse(line.holiday_window_id)
        self.assertEqual(line.date_planned, target_date)
        # Note standard : pas de mention fenêtre
        note = line.activity_id.note or ''
        self.assertNotIn('Rentrée', note)

    # ==================================================================
    # AC9 — Fenêtre désactivée / priorité / idempotence
    # ==================================================================

    def test_materialize_skips_inactive_window(self):
        """AC9 — fenêtre désactivée chevauche → ignorée."""
        self.win_tabaski.write({'active': False})
        try:
            target_date = date(2026, 5, 28)
            schedule = self._create_schedule_direct(
                self.plan_std18m, self.partner_adult,
                delivered_date=target_date - timedelta(days=30),
            )
            line = schedule.line_ids.sorted('sequence')[0]
            line.write({'date_planned': target_date})
            line._materialize_step_activity()
            line.invalidate_recordset()
            # Aucune fenêtre appliquée
            self.assertFalse(line.holiday_window_id)
            self.assertEqual(line.date_planned, target_date)
        finally:
            self.win_tabaski.write({'active': True})

    def test_materialize_priority_postpone_wins_over_switch_soft(self):
        """AC9 — postpone_to_end l'emporte sur switch_channel_soft en chevauchement."""
        # Créer une fenêtre switch_soft qui chevauche Tabaski (2026-05-27 → 2026-05-29)
        Window = self.env['optical.followup.holiday.window']
        overlap = Window.create({
            'name': 'Chevauchement soft',
            'sequence': 5,  # avant Tabaski (30)
            'behavior': 'switch_channel_soft',
            'suggested_channel': 'whatsapp',
            'date_start_civil': '05-27',
            'date_end_civil': '05-30',
        })
        try:
            target_date = date(2026, 5, 28)
            schedule = self._create_schedule_direct(
                self.plan_std18m, self.partner_adult,
                delivered_date=target_date - timedelta(days=30),
            )
            line = schedule.line_ids.sorted('sequence')[0]
            line.write({'date_planned': target_date})
            with mute_logger('odoo.addons.optical_crm_followup.models.optical_followup_holiday_window'):
                line._materialize_step_activity()
            line.invalidate_recordset()
            # Tabaski (postpone_to_end) doit gagner malgré sequence inférieure de overlap
            self.assertEqual(line.holiday_window_id, self.win_tabaski)
            self.assertEqual(line.date_planned, date(2026, 5, 30))
        finally:
            overlap.unlink()

    def test_materialize_postpone_cascade_across_adjacent_windows(self):
        """Revue S16.1 M1 — 2 fenêtres postpone_to_end adjacentes → cascade.

        Simule le cas où le PO transforme Ramadan en postpone_to_end : une
        ligne tombant en Ramadan (fin le 2026-03-19) doit être repoussée
        au-delà d'Aïd al-Fitr (fin 2026-03-21), soit 2026-03-22, et non
        atterrir le 1ᵉʳ jour d'Aïd (2026-03-20).
        """
        original_ramadan_behavior = self.win_ramadan.behavior
        self.win_ramadan.write({'behavior': 'postpone_to_end'})
        try:
            target_date = date(2026, 3, 18)  # avant-dernier jour de Ramadan
            schedule = self._create_schedule_direct(
                self.plan_std18m, self.partner_adult,
                delivered_date=target_date - timedelta(days=30),
            )
            line = schedule.line_ids.sorted('sequence')[0]
            line.write({'date_planned': target_date})
            line._materialize_step_activity()
            line.invalidate_recordset()
            # La ligne doit finir APRÈS Aïd al-Fitr (fin 2026-03-21), pas en plein Aïd.
            self.assertEqual(line.date_planned, date(2026, 3, 22))
            # holiday_window_id doit refléter la DERNIÈRE fenêtre traversée
            # (Aïd al-Fitr) — celle qui a poussé au bout.
            self.assertEqual(line.holiday_window_id, self.win_aid_fitr)
            self.assertEqual(line.activity_id.date_deadline, date(2026, 3, 22))
        finally:
            self.win_ramadan.write({'behavior': original_ramadan_behavior})

    def test_materialize_idempotent_if_holiday_window_already_set(self):
        """AC6 — 2ᵉ passage cron : pas de re-report, pas de doublon activité."""
        target_date = date(2026, 5, 28)
        schedule = self._create_schedule_direct(
            self.plan_std18m, self.partner_adult,
            delivered_date=target_date - timedelta(days=30),
        )
        line = schedule.line_ids.sorted('sequence')[0]
        line.write({'date_planned': target_date})
        line._materialize_step_activity()
        line.invalidate_recordset()
        first_activity = line.activity_id
        first_date_planned = line.date_planned
        # 2ᵉ passage
        line._materialize_step_activity()
        line.invalidate_recordset()
        self.assertEqual(line.activity_id, first_activity)
        self.assertEqual(line.date_planned, first_date_planned)

    # ==================================================================
    # Non-régression 15.2
    # ==================================================================

    def test_materialize_without_any_window_preserves_std_behavior(self):
        """15.2 — aucune fenêtre active → comportement 15.2 inchangé."""
        # Désactiver toutes les fenêtres
        all_windows = self.env['optical.followup.holiday.window'].search([])
        all_windows.write({'active': False})
        try:
            schedule = self._create_schedule_direct(
                self.plan_std18m, self.partner_adult,
            )
            line = schedule.line_ids.sorted('sequence')[0]
            line.write({'date_planned': fields.Date.add(fields.Date.today(), days=3)})
            line._materialize_step_activity()
            line.invalidate_recordset()
            self.assertTrue(line.activity_id)
            self.assertFalse(line.holiday_window_id)
            # Note standard : pas de mention fenêtre
            note = line.activity_id.note or ''
            self.assertNotIn('Reporté par fenêtre', note)
            self.assertNotIn('Période', note)
        finally:
            all_windows.write({'active': True})
