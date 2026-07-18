# -*- coding: utf-8 -*-
from datetime import date, datetime, timedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'optical_crm_followup')
class TestS02Execution(TransactionCase):
    """Story 15.2 — Moteur calendriers, activités J-3, preset Standard 18m,
    alerte picking > 7 j."""

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

        # Boutique dédiée
        cls.warehouse = cls.env['stock.warehouse'].create({
            'name': 'Boutique S02',
            'code': 'S02',
        })

        # Users
        cls.user_referent = cls.env['res.users'].with_context(
            no_reset_password=True
        ).create({
            'name': 'Commercial S02',
            'login': 'commercial_s02',
            'email': 'commercial_s02@test.com',
            'groups_id': [Command.set([cls.group_optical_user.id] + cls.base_groups)],
            'optical_warehouse_ids': [Command.set([cls.warehouse.id])],
        })
        cls.user_manager = cls.env['res.users'].with_context(
            no_reset_password=True
        ).create({
            'name': 'Manager S02',
            'login': 'manager_s02',
            'email': 'manager_s02@test.com',
            'groups_id': [Command.set([cls.group_optical_manager.id] + cls.base_groups)],
        })

        # Partners
        cls.partner_adult = cls.env['res.partner'].create({
            'name': 'Client Adulte S02',
            'birthdate': date.today() - timedelta(days=int(30 * 365.25)),
            'email': 'adult_s02@test.com',
        })
        cls.partner_no_consent = cls.env['res.partner'].create({
            'name': 'Client Sans Consent',
        })
        cls.partner_optout = cls.env['res.partner'].create({
            'name': 'Client OptOut',
        })
        cls.partner_minor = cls.env['res.partner'].create({
            'name': 'Client Mineur S02',
            'birthdate': date.today() - timedelta(days=int(15 * 365.25)),
        })
        # Consent OK sur adulte
        cls.partner_adult.write({'optical_followup_consent': True})
        # Optout
        cls.partner_optout.write({
            'optical_followup_consent': True,
            'optical_followup_optout': True,
        })
        # Minor with consent but no legal rep
        cls.partner_minor.write({'optical_followup_consent': True})

        # Produits — unifocal (par défaut mapping to fallback 'any')
        cls.product_unifocal = cls.env['product.product'].create({
            'name': 'Verre Unifocal S02',
            'type': 'consu',
            'list_price': 100.0,
        })
        cls.product_unifocal.product_tmpl_id.write({
            'optical_type': 'lens',
            'lens_design': 'single_vision',
        })
        cls.product_progressive = cls.env['product.product'].create({
            'name': 'Verre Progressif S02',
            'type': 'consu',
            'list_price': 200.0,
        })
        cls.product_progressive.product_tmpl_id.write({
            'optical_type': 'lens',
            'lens_design': 'progressive',
        })
        cls.product_contact = cls.env['product.product'].create({
            'name': 'Lentille S02',
            'type': 'consu',
            'list_price': 50.0,
        })
        cls.product_contact.product_tmpl_id.write({
            'optical_type': 'contact_lens',
        })

        # Plan Standard 18m livré par le module
        cls.plan_std18m = cls.env.ref('optical_crm_followup.plan_standard_18m')

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_sale_order(self, partner, product=None, user=None):
        product = product or self.product_unifocal
        vals = {
            'partner_id': partner.id,
            'order_line': [Command.create({
                'product_id': product.id,
                'product_uom_qty': 1,
            })],
        }
        if user:
            vals['user_id'] = user.id
        else:
            vals['user_id'] = self.user_referent.id
        so = self.env['sale.order'].create(vals)
        return so

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

    # ==================================================================
    # AC1 — Création automatique du calendrier au picking outgoing
    # ==================================================================

    def test_hook_creates_schedule_on_picking_done(self):
        """AC1 happy path — consent OK, picking done, schedule + 3 lignes créés."""
        so = self._make_sale_order(self.partner_adult)
        pickings = self._confirm_and_deliver(so)

        schedule = self.env['optical.followup.schedule'].search([
            ('partner_id', '=', self.partner_adult.id),
            ('state', '=', 'running'),
        ])
        self.assertEqual(len(schedule), 1)
        self.assertEqual(schedule.plan_id, self.plan_std18m)
        self.assertEqual(schedule.sale_order_id, so)
        # La warehouse est celle du picking outgoing (route Odoo native — WH par défaut)
        self.assertEqual(schedule.warehouse_id, pickings.picking_type_id.warehouse_id)
        self.assertEqual(len(schedule.line_ids), 3)
        self.assertTrue(all(l.state == 'pending' for l in schedule.line_ids))
        self.assertEqual(so.followup_schedule_id, schedule)

    def test_hook_skips_if_no_consent(self):
        """AC6 — partner sans consent : aucun schedule créé."""
        so = self._make_sale_order(self.partner_no_consent)
        self._confirm_and_deliver(so)
        schedules = self.env['optical.followup.schedule'].search([
            ('partner_id', '=', self.partner_no_consent.id),
        ])
        self.assertFalse(schedules)
        self.assertFalse(so.followup_schedule_id)

    def test_hook_skips_if_optout(self):
        """AC6 — partner optout : aucun schedule créé."""
        so = self._make_sale_order(self.partner_optout)
        self._confirm_and_deliver(so)
        schedules = self.env['optical.followup.schedule'].search([
            ('partner_id', '=', self.partner_optout.id),
        ])
        self.assertFalse(schedules)

    def test_hook_skips_if_minor_no_legal_rep(self):
        """AC6 — partner mineur sans consent RL : aucun schedule créé."""
        so = self._make_sale_order(self.partner_minor)
        self._confirm_and_deliver(so)
        schedules = self.env['optical.followup.schedule'].search([
            ('partner_id', '=', self.partner_minor.id),
        ])
        self.assertFalse(schedules)

    def test_hook_delivered_date_from_picking(self):
        """AC1 — delivered_date = picking.date_done (fallback aujourd'hui)."""
        so = self._make_sale_order(self.partner_adult)
        pickings = self._confirm_and_deliver(so)
        schedule = so.followup_schedule_id
        self.assertTrue(schedule)
        expected = fields.Date.to_date(pickings[0].date_done) or fields.Date.today()
        self.assertEqual(schedule.delivered_date, expected)
        # Vérifier que les lignes ont bien date_planned = delivered_date + offset
        step_j30 = self.env.ref('optical_crm_followup.plan_standard_18m_step_j30')
        line_j30 = schedule.line_ids.filtered(lambda l: l.step_id == step_j30)
        self.assertEqual(len(line_j30), 1)
        self.assertEqual(
            line_j30.date_planned,
            fields.Date.add(schedule.delivered_date, days=30),
        )

    # ==================================================================
    # AC2 — Sélection du preset via optical_type
    # ==================================================================

    def test_select_plan_returns_fallback_std18m(self):
        """AC2 — SO sans produit progressive/lentilles → plan_standard_18m."""
        so = self._make_sale_order(self.partner_adult, product=self.product_unifocal)
        plan = self.env['optical.followup.plan']._select_for_sale_order(so)
        self.assertEqual(plan, self.plan_std18m)

    def test_select_plan_returns_empty_recordset_if_no_active_fallback(self):
        """AC2 — désactiver plan any → recordset vide + hook ne crée rien."""
        self.plan_std18m.write({'active': False})
        try:
            so = self._make_sale_order(self.partner_adult)
            self._confirm_and_deliver(so)
            schedules = self.env['optical.followup.schedule'].search([
                ('partner_id', '=', self.partner_adult.id),
            ])
            self.assertFalse(schedules)
            plan = self.env['optical.followup.plan']._select_for_sale_order(so)
            self.assertFalse(plan)
        finally:
            self.plan_std18m.write({'active': True})

    def test_std18m_preset_editable_post_install(self):
        """AC2 — modifier offset_days d'un step est bien reflété par les nouveaux schedules."""
        step_j30 = self.env.ref('optical_crm_followup.plan_standard_18m_step_j30')
        original = step_j30.offset_days
        try:
            step_j30.write({'offset_days': 45})
            so = self._make_sale_order(self.partner_adult)
            self._confirm_and_deliver(so)
            schedule = so.followup_schedule_id
            line_j30 = schedule.line_ids.filtered(lambda l: l.step_id == step_j30)
            self.assertEqual(
                line_j30.date_planned,
                fields.Date.add(schedule.delivered_date, days=45),
            )
        finally:
            step_j30.write({'offset_days': original})

    # ==================================================================
    # AC3 — Matérialisation activité J-3
    # ==================================================================

    def _create_schedule_direct(self, partner, delivered_days_ago=0):
        """Fabrique un schedule direct (sans passer par le hook)."""
        delivered_date = fields.Date.today() - timedelta(days=delivered_days_ago)
        schedule = self.env['optical.followup.schedule'].create({
            'name': 'SCH-S02-DIRECT-%s' % partner.id,
            'partner_id': partner.id,
            'warehouse_id': self.warehouse.id,
            'plan_id': self.plan_std18m.id,
            'referent_user_id': self.user_referent.id,
            'delivered_date': delivered_date,
            'state': 'running',
        })
        for step in self.plan_std18m.step_ids:
            self.env['optical.followup.schedule.line'].create({
                'schedule_id': schedule.id,
                'step_id': step.id,
                'sequence': step.sequence,
                'date_planned': fields.Date.add(delivered_date, days=step.offset_days),
                'date_planned_original': fields.Date.add(delivered_date, days=step.offset_days),
                'state': 'pending',
            })
        return schedule

    def test_cron_materializes_activity_at_j_minus_3(self):
        """AC3 — cron crée une mail.activity pour les lignes date_planned = today+3."""
        # Créer un schedule et forcer une ligne à date_planned = today + 3
        schedule = self._create_schedule_direct(self.partner_adult)
        line = schedule.line_ids[0]
        line.write({'date_planned': fields.Date.add(fields.Date.today(), days=3)})

        self.env['optical.followup.schedule']._run_daily_cron()

        line.invalidate_recordset()
        self.assertTrue(line.activity_id)
        self.assertEqual(line.activity_id.res_model, 'res.partner')
        self.assertEqual(line.activity_id.res_id, self.partner_adult.id)
        self.assertEqual(line.activity_id.user_id, self.user_referent)
        self.assertEqual(line.activity_id.date_deadline, line.date_planned)

    def test_cron_idempotent_on_already_materialized_line(self):
        """AC3 — 2ᵉ passe du cron ne crée pas de doublon."""
        schedule = self._create_schedule_direct(self.partner_adult)
        line = schedule.line_ids[0]
        line.write({'date_planned': fields.Date.add(fields.Date.today(), days=3)})
        self.env['optical.followup.schedule']._run_daily_cron()
        activity_first = line.activity_id
        self.assertTrue(activity_first)
        # 2ᵉ passe
        self.env['optical.followup.schedule']._run_daily_cron()
        line.invalidate_recordset()
        self.assertEqual(line.activity_id, activity_first)

    def test_cron_note_contains_channel_role_and_template_hint(self):
        """AC3 — la note d'activité contient canal + rôle recommandés."""
        schedule = self._create_schedule_direct(self.partner_adult)
        line = schedule.line_ids[0]
        line.write({'date_planned': fields.Date.add(fields.Date.today(), days=3)})
        self.env['optical.followup.schedule']._run_daily_cron()
        line.invalidate_recordset()
        note = line.activity_id.note or ''
        self.assertIn('Canal recommandé', note)
        self.assertIn('Rôle recommandé', note)

    # ==================================================================
    # AC4 — Overdue
    # ==================================================================

    def test_cron_marks_line_overdue_if_planned_before_today(self):
        """AC4 — cron marque overdue les lignes pending dont date_planned < today."""
        schedule = self._create_schedule_direct(self.partner_adult, delivered_days_ago=100)
        # Les lignes ont des date_planned potentiellement < today
        line = schedule.line_ids[0]  # step J+30 → si delivered_days_ago=100 → today-70
        line.write({'date_planned': fields.Date.subtract(fields.Date.today(), days=1)})

        self.env['optical.followup.schedule']._run_daily_cron()
        line.invalidate_recordset()
        self.assertEqual(line.state, 'overdue')

    # ==================================================================
    # AC5 — Outcome via wizard
    # ==================================================================

    def test_wizard_marks_line_done_and_persists_outcome(self):
        """AC5 — wizard.action_confirm passe la ligne à done + outcome + activité fermée."""
        schedule = self._create_schedule_direct(self.partner_adult)
        line = schedule.line_ids[0]
        # Matérialiser l'activité en direct
        line._materialize_step_activity()
        line.invalidate_recordset()
        activity = line.activity_id
        self.assertTrue(activity)

        wizard = self.env['optical.followup.line.feedback.wizard'].create({
            'line_id': line.id,
            'outcome': 'answered',
            'note': "Client satisfait",
        })
        wizard.action_confirm()

        line.invalidate_recordset()
        self.assertEqual(line.state, 'done')
        self.assertEqual(line.outcome, 'answered')
        self.assertEqual(line.outcome_note, "Client satisfait")
        # Activité fermée (action_feedback → mail.message et unlink)
        remaining = self.env['mail.activity'].search([('id', '=', activity.id)])
        self.assertFalse(remaining, "L'activité doit être fermée après action_feedback")

    def test_first_contact_date_set_on_first_done_line(self):
        """AC5 — first_contact_date est renseigné à la 1ʳᵉ ligne done, pas la 2ᵉ."""
        schedule = self._create_schedule_direct(self.partner_adult)
        lines = schedule.line_ids.sorted('sequence')
        self.assertFalse(schedule.first_contact_date)

        lines[0]._mark_done('answered')
        schedule.invalidate_recordset()
        self.assertEqual(schedule.first_contact_date, fields.Date.today())

        # Simuler une avance d'un jour pour la 2ᵉ ligne — pas de modification du champ
        first_contact = schedule.first_contact_date
        lines[1]._mark_done('unreachable')
        schedule.invalidate_recordset()
        self.assertEqual(schedule.first_contact_date, first_contact)

    # ==================================================================
    # AC7 — Alerte picking > 7 j
    # ==================================================================

    def test_cron_creates_late_picking_activity_after_7_days(self):
        """AC7 — SO date_order = today-8j avec picking encore ouvert : warning créé."""
        so = self._make_sale_order(self.partner_adult)
        so.action_confirm()
        # Ne pas valider le picking : reste en assigned/waiting
        # Antidater date_order via write direct (SQL bypass) — champs Datetime
        past = datetime.now() - timedelta(days=8)
        self.env.cr.execute(
            "UPDATE sale_order SET date_order = %s WHERE id = %s",
            (past, so.id),
        )
        so.invalidate_recordset()

        self.env['optical.followup.schedule']._run_daily_cron()

        so.invalidate_recordset()
        self.assertTrue(so.picking_late_alert_sent)
        acts = self.env['mail.activity'].search([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', so.id),
        ])
        self.assertTrue(acts, "Une activité warning doit avoir été créée sur la SO")

    def test_cron_late_picking_idempotent(self):
        """AC7 — 2ᵉ passe du cron ne crée pas de 2ᵉ warning."""
        so = self._make_sale_order(self.partner_adult)
        so.action_confirm()
        past = datetime.now() - timedelta(days=8)
        self.env.cr.execute(
            "UPDATE sale_order SET date_order = %s WHERE id = %s",
            (past, so.id),
        )
        so.invalidate_recordset()

        self.env['optical.followup.schedule']._run_daily_cron()
        count_first = self.env['mail.activity'].search_count([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', so.id),
        ])
        self.env['optical.followup.schedule']._run_daily_cron()
        count_second = self.env['mail.activity'].search_count([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', so.id),
        ])
        self.assertEqual(count_first, count_second)

    def test_cron_late_picking_activity_closed_when_picking_validated(self):
        """AC7 — picking validé après alerte : warning fermé + chatter log."""
        so = self._make_sale_order(self.partner_adult)
        so.action_confirm()
        past = datetime.now() - timedelta(days=8)
        self.env.cr.execute(
            "UPDATE sale_order SET date_order = %s WHERE id = %s",
            (past, so.id),
        )
        so.invalidate_recordset()

        self.env['optical.followup.schedule']._run_daily_cron()
        so.invalidate_recordset()
        self.assertTrue(so.picking_late_alert_sent)

        # Valider le picking
        pickings = so.picking_ids.filtered(
            lambda p: p.picking_type_id.code == 'outgoing'
        )
        for picking in pickings:
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
            picking.button_validate()

        # 2ᵉ passe : l'alerte doit disparaître
        self.env['optical.followup.schedule']._run_daily_cron()
        acts = self.env['mail.activity'].search([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', so.id),
            ('summary', '=', "Picking en attente > 7 j — remise non validée"),
        ])
        self.assertFalse(acts, "L'activité warning doit avoir été fermée")

    # ==================================================================
    # AC8 — Réachat anticipé
    # ==================================================================

    def test_reachat_fulfills_old_schedule_and_creates_new(self):
        """AC8 — nouveau picking pour un partner avec schedule running :
        ancien passe fulfilled, lignes pending cancelled, nouveau schedule créé."""
        so1 = self._make_sale_order(self.partner_adult)
        self._confirm_and_deliver(so1)
        schedule_old = so1.followup_schedule_id
        self.assertEqual(schedule_old.state, 'running')
        old_activity_ids = schedule_old.line_ids.mapped('activity_id').ids

        # Nouveau picking
        so2 = self._make_sale_order(self.partner_adult)
        self._confirm_and_deliver(so2)

        schedule_old.invalidate_recordset()
        self.assertEqual(schedule_old.state, 'fulfilled')
        # Toutes les lignes pending → cancelled avec note réachat
        cancelled = schedule_old.line_ids.filtered(lambda l: l.state == 'cancelled')
        self.assertTrue(cancelled)
        for line in cancelled:
            self.assertIn("Réachat anticipé", line.outcome_note or '')

        # Activités anciennes supprimées (si elles existaient)
        if old_activity_ids:
            remaining = self.env['mail.activity'].search(
                [('id', 'in', old_activity_ids)]
            )
            self.assertFalse(remaining)

        # Nouveau schedule créé
        new_schedule = so2.followup_schedule_id
        self.assertTrue(new_schedule)
        self.assertNotEqual(new_schedule.id, schedule_old.id)
        self.assertEqual(new_schedule.state, 'running')

    # ==================================================================
    # AC9 — Digest overdue
    # ==================================================================

    def test_digest_mail_sent_to_referent_with_overdue_lines(self):
        """AC9 — digest envoie 1 mail par référent ayant au moins 1 overdue."""
        schedule = self._create_schedule_direct(self.partner_adult, delivered_days_ago=100)
        # Marquer une ligne comme overdue
        line = schedule.line_ids[0]
        line.write({
            'date_planned': fields.Date.subtract(fields.Date.today(), days=5),
            'state': 'overdue',
        })

        # On patch send_mail pour capturer sans réellement envoyer
        sent = []
        original_send_mail = type(self.env['mail.template']).send_mail

        def _capture(self_tpl, res_id, **kwargs):
            sent.append({
                'template': self_tpl.id,
                'res_id': res_id,
                'email_to': (kwargs.get('email_values') or {}).get('email_to'),
            })
            return True

        type(self.env['mail.template']).send_mail = _capture
        try:
            self.env['optical.followup.schedule']._run_digest_overdue()
        finally:
            type(self.env['mail.template']).send_mail = original_send_mail

        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]['email_to'], self.user_referent.partner_id.email)

    # ==================================================================
    # Non-régressions revue code S15.2
    # ==================================================================

    def test_reachat_scoped_by_warehouse(self):
        """M1 revue — un réachat dans une autre boutique NE clôture PAS
        le calendrier actif de la boutique d'origine."""
        # Créer un 2ᵉ warehouse distinct
        wh_other = self.env['stock.warehouse'].create({
            'name': 'Boutique S02 Autre',
            'code': 'S02B',
        })
        # 1ʳᵉ SO/livraison dans warehouse par défaut
        so1 = self._make_sale_order(self.partner_adult)
        self._confirm_and_deliver(so1)
        schedule_1 = so1.followup_schedule_id
        self.assertEqual(schedule_1.state, 'running')

        # 2ᵉ SO dans wh_other → doit créer un 2ᵉ schedule sans clôturer le 1ᵉʳ
        so2 = self.env['sale.order'].create({
            'partner_id': self.partner_adult.id,
            'warehouse_id': wh_other.id,
            'user_id': self.user_referent.id,
            'order_line': [Command.create({
                'product_id': self.product_unifocal.id,
                'product_uom_qty': 1,
            })],
        })
        self._confirm_and_deliver(so2)

        schedule_1.invalidate_recordset()
        self.assertEqual(
            schedule_1.state, 'running',
            "Le schedule de la boutique d'origine doit rester actif quand "
            "le réachat a lieu dans une autre boutique.",
        )
        schedule_2 = so2.followup_schedule_id
        self.assertTrue(schedule_2)
        self.assertEqual(schedule_2.warehouse_id, wh_other)
        self.assertNotEqual(schedule_2, schedule_1)

    def test_mark_done_twice_raises_user_error(self):
        """M2 revue — rappeler _mark_done sur une ligne déjà done
        doit lever UserError plutôt que d'écraser l'outcome."""
        schedule = self._create_schedule_direct(self.partner_adult)
        line = schedule.line_ids[0]
        line._materialize_step_activity()
        line._mark_done('answered')

        with self.assertRaises(UserError):
            line._mark_done('purchased')

    def test_late_picking_closure_via_activity_pointer(self):
        """M3 revue — la fermeture de l'alerte s'appuie sur
        picking_late_alert_activity_id, insensible à la traduction du summary."""
        so = self._make_sale_order(self.partner_adult)
        so.action_confirm()
        past = datetime.now() - timedelta(days=8)
        self.env.cr.execute(
            "UPDATE sale_order SET date_order = %s WHERE id = %s",
            (past, so.id),
        )
        so.invalidate_recordset()

        self.env['optical.followup.schedule']._run_daily_cron()
        so.invalidate_recordset()
        self.assertTrue(so.picking_late_alert_sent)
        self.assertTrue(
            so.picking_late_alert_activity_id,
            "Le pointeur direct vers l'activité doit être renseigné.",
        )

        # Falsifier le summary de l'activité (simulation langue différente)
        activity = so.picking_late_alert_activity_id
        activity.summary = "STRING TOTALEMENT DIFFERENT"

        # Valider le picking et rejouer le cron
        pickings = so.picking_ids.filtered(
            lambda p: p.picking_type_id.code == 'outgoing'
        )
        for picking in pickings:
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
            picking.button_validate()

        self.env['optical.followup.schedule']._run_daily_cron()
        # L'ancienne activité doit avoir été supprimée malgré le summary
        # divergent : la closure suit le pointeur direct, pas le texte.
        remaining = self.env['mail.activity'].search([('id', '=', activity.id)])
        self.assertFalse(
            remaining,
            "L'activité doit être fermée via le pointeur direct.",
        )

    def test_digest_skips_user_without_email(self):
        """AC9 — référent sans email : log info, aucun mail envoyé."""
        # Créer un référent sans email
        user_no_email = self.env['res.users'].with_context(
            no_reset_password=True
        ).create({
            'name': 'Referent Sans Email',
            'login': 'no_email_ref',
            'email': False,
            'groups_id': [Command.set([self.group_optical_user.id] + self.base_groups)],
        })
        user_no_email.partner_id.email = False

        schedule = self._create_schedule_direct(self.partner_adult)
        schedule.write({'referent_user_id': user_no_email.id})
        line = schedule.line_ids[0]
        line.write({
            'date_planned': fields.Date.subtract(fields.Date.today(), days=5),
            'state': 'overdue',
        })

        # Ne doit pas lever d'exception, juste skip
        mail_before = self.env['mail.mail'].search_count([])
        self.env['optical.followup.schedule']._run_digest_overdue()
        mail_after = self.env['mail.mail'].search_count([])
        # Aucun mail envoyé au referent sans email (les autres schedules du setUp
        # peuvent envoyer — on vérifie plutôt qu'aucun ciblé au no_email n'existe)
        mails_to_user = self.env['mail.mail'].search([
            ('email_to', 'ilike', 'no_email_ref'),
        ])
        self.assertFalse(mails_to_user)
