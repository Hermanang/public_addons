# -*- coding: utf-8 -*-
"""Story 16.2 — Suspension SAV : pause automatique, reprise, multi-tickets,
recalcul dates, multi-schedules, non-régression cascade opt-out et cron."""
from datetime import date, timedelta

from odoo import Command, fields
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install', 'optical_crm_followup')
class TestS04SavPause(TransactionCase):

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
            'name': 'Boutique S04',
            'code': 'S04',
        })
        cls.warehouse_2 = cls.env['stock.warehouse'].create({
            'name': 'Boutique S04-B',
            'code': 'S04B',
        })

        cls.user_referent = cls.env['res.users'].with_context(
            no_reset_password=True
        ).create({
            'name': 'Commercial S04',
            'login': 'commercial_s04',
            'email': 'commercial_s04@test.com',
            'groups_id': [Command.set([cls.group_optical_user.id] + cls.base_groups)],
            'optical_warehouse_ids': [Command.set([cls.warehouse.id, cls.warehouse_2.id])],
        })
        cls.user_manager = cls.env['res.users'].with_context(
            no_reset_password=True
        ).create({
            'name': 'Manager S04',
            'login': 'manager_s04',
            'email': 'manager_s04@test.com',
            'groups_id': [Command.set([cls.group_optical_manager.id] + cls.base_groups)],
        })

        # Partners consentants (adultes)
        cls.partner_a = cls.env['res.partner'].create({
            'name': 'Client SAV A',
            'birthdate': date.today() - timedelta(days=int(30 * 365.25)),
            'email': 'sav_a@test.com',
        })
        cls.partner_a.write({'optical_followup_consent': True})
        cls.partner_b = cls.env['res.partner'].create({
            'name': 'Client SAV B',
            'birthdate': date.today() - timedelta(days=int(30 * 365.25)),
            'email': 'sav_b@test.com',
        })
        cls.partner_b.write({'optical_followup_consent': True})

        cls.plan_std18m = cls.env.ref('optical_crm_followup.plan_standard_18m')

        # Stages helpdesk_mgmt livrés à l'installation
        cls.stage_new = cls.env.ref('helpdesk_mgmt.helpdesk_ticket_stage_new')
        cls.stage_done = cls.env.ref('helpdesk_mgmt.helpdesk_ticket_stage_done')

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_schedule_direct(self, partner, warehouse=None, delivered_days_ago=0):
        warehouse = warehouse or self.warehouse
        delivered_date = fields.Date.today() - timedelta(days=delivered_days_ago)
        schedule = self.env['optical.followup.schedule'].create({
            'name': 'SCH-S04-%s-%s' % (partner.id, warehouse.id),
            'partner_id': partner.id,
            'warehouse_id': warehouse.id,
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

    def _make_ticket(self, partner, stage=None):
        return self.env['helpdesk.ticket'].create({
            'name': 'Ticket SAV %s' % (partner.name if partner else 'anon'),
            'description': '<p>Test SAV</p>',
            'partner_id': partner.id if partner else False,
            'stage_id': (stage or self.stage_new).id,
        })

    def _materialize_activity_for_line(self, line):
        """Force la matérialisation d'une mail.activity sur la ligne (simule cron)."""
        line.write({'date_planned': fields.Date.add(fields.Date.today(), days=3)})
        line._materialize_step_activity()
        return line.activity_id

    # ==================================================================
    # AC1 — Pause SAV à la création du ticket
    # ==================================================================

    def test_ticket_creation_pauses_running_schedule(self):
        """AC1 happy path — création ticket → schedule paused, lignes paused,
        activités unlink, chatter posté."""
        schedule = self._create_schedule_direct(self.partner_a)
        # Matérialiser une activité pour vérifier son unlink
        activity = self._materialize_activity_for_line(schedule.line_ids[0])
        self.assertTrue(activity.id)

        self._make_ticket(self.partner_a)

        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'paused')
        self.assertEqual(schedule.pause_reason, 'sav_open')
        self.assertEqual(schedule.sav_paused_date, fields.Date.today())

        paused_lines = schedule.line_ids.filtered(lambda l: l.state == 'paused')
        self.assertTrue(paused_lines, "Les lignes doivent passer en paused")

        remaining_activity = self.env['mail.activity'].search([
            ('id', '=', activity.id)
        ])
        self.assertFalse(remaining_activity, "L'activité doit avoir été supprimée")

        messages = self.partner_a.message_ids.mapped('body')
        self.assertTrue(any('suspendu' in (m or '').lower() for m in messages))

    def test_ticket_creation_no_partner_is_noop(self):
        """AC10 — ticket sans partner_id : aucune action, aucune exception."""
        schedule = self._create_schedule_direct(self.partner_a)
        # Ticket interne sans partner
        self._make_ticket(partner=None)
        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'running', "Aucune pause attendue")

    def test_ticket_creation_partner_without_schedule_is_noop(self):
        """AC10 — ticket sur partner sans schedule : aucune action."""
        self._make_ticket(self.partner_b)
        schedules = self.env['optical.followup.schedule'].search([
            ('partner_id', '=', self.partner_b.id)
        ])
        self.assertFalse(schedules)

    def test_ticket_write_partner_id_change_syncs_both(self):
        """AC1 second Given — write partner_id : sync ancien + nouveau."""
        # Setup : partner_a running, partner_b paused SAV avec 1 ticket
        schedule_a = self._create_schedule_direct(self.partner_a)
        schedule_b = self._create_schedule_direct(self.partner_b)
        ticket = self._make_ticket(self.partner_b)  # → partner_b paused

        schedule_b.invalidate_recordset()
        self.assertEqual(schedule_b.state, 'paused')

        # Basculer le ticket vers partner_a
        ticket.write({'partner_id': self.partner_a.id})

        schedule_a.invalidate_recordset()
        schedule_b.invalidate_recordset()
        self.assertEqual(schedule_a.state, 'paused', "partner_a doit passer en paused")
        self.assertEqual(
            schedule_b.state, 'running',
            "partner_b doit reprendre (plus aucun ticket ouvert le concernant)",
        )

    # ==================================================================
    # AC2 — Reprise à la clôture
    # ==================================================================

    def test_close_last_open_ticket_resumes_schedule(self):
        """AC2 — clôture du dernier ticket : schedule resume, chatter posté."""
        schedule = self._create_schedule_direct(self.partner_a)
        ticket = self._make_ticket(self.partner_a)
        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'paused')

        ticket.write({'stage_id': self.stage_done.id})

        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'running')
        pending_lines = schedule.line_ids.filtered(lambda l: l.state == 'pending')
        self.assertTrue(pending_lines)

        # Audit conservé (D-RESUME-DATE = conservation)
        self.assertEqual(schedule.pause_reason, 'sav_open')
        self.assertTrue(schedule.sav_paused_date)

    def test_close_one_of_two_tickets_keeps_paused(self):
        """AC2 second Given — 2 tickets ouverts, clore 1 : reste paused
        ET aucun chatter réouverture parasite (bug H2 revue code)."""
        schedule = self._create_schedule_direct(self.partner_a)
        ticket_1 = self._make_ticket(self.partner_a)
        ticket_2 = self._make_ticket(self.partner_a)
        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'paused')

        messages_before = len(self.partner_a.message_ids)
        ticket_1.write({'stage_id': self.stage_done.id})
        schedule.invalidate_recordset()
        self.assertEqual(
            schedule.state, 'paused',
            "Doit rester paused tant qu'un ticket est ouvert",
        )
        # ticket_2 encore ouvert
        self.assertFalse(ticket_2.closed)

        # AC2 « aucune modification » : la clôture d'un ticket parmi plusieurs
        # ne doit poster AUCUN chatter réouverture ni pause.
        messages_after = len(self.partner_a.message_ids)
        self.assertEqual(
            messages_after, messages_before,
            "Clôturer 1 ticket parmi plusieurs ne doit poster aucun chatter",
        )

    def test_reopen_closed_ticket_re_pauses_schedule(self):
        """AC1 5ᵉ Given — schedule running (jamais paused),
        ré-ouverture d'un ticket clos → bascule paused avec chatter
        « suspendu automatiquement » (pas « rouvert »)."""
        schedule = self._create_schedule_direct(self.partner_a)
        # Créer directement un ticket clos (aucune pause)
        ticket = self._make_ticket(self.partner_a, stage=self.stage_done)
        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'running', "Ticket clos ne doit pas pauser")

        # Ré-ouvrir le ticket
        ticket.write({'stage_id': self.stage_new.id})
        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'paused')
        self.assertEqual(schedule.pause_reason, 'sav_open')

        bodies = self.partner_a.message_ids.mapped('body') or []
        self.assertTrue(
            any('suspendu' in (b or '').lower() for b in bodies),
            "Chatter « suspendu automatiquement » attendu à la 1ʳᵉ pause",
        )

    def test_reopen_closed_ticket_on_paused_schedule_posts_rouvert_chatter(self):
        """AC2 3ᵉ Given — schedule déjà paused (2 tickets clos), ré-ouvrir
        1 ticket → schedule reste paused ET chatter « rouvert » posté.

        Ce test verrouille le cas légitime de la branche réouverture après
        la correction des bugs H1/H2/H3 (revue code)."""
        schedule = self._create_schedule_direct(self.partner_a)
        # Setup : 2 tickets — 1 ouvert (met en pause) + 1 clos dès le départ
        ticket_1 = self._make_ticket(self.partner_a)  # open → paused
        ticket_2 = self._make_ticket(self.partner_a, stage=self.stage_done)
        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'paused')

        # Ré-ouverture réelle : ticket_2 passe closed→open, schedule reste paused
        messages_before = len(self.partner_a.message_ids)
        ticket_2.write({'stage_id': self.stage_new.id})
        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'paused', "Doit rester paused")

        messages_after = list(self.partner_a.message_ids)
        new_messages = messages_after[:len(messages_after) - messages_before]
        bodies = [m.body or '' for m in new_messages]
        self.assertTrue(
            any('rouvert' in b for b in bodies),
            "Chatter « rouvert » attendu à la ré-ouverture explicite d'un ticket clos",
        )
        # Le ticket nommé doit bien être ticket_2 (celui rouvert), pas ticket_1
        self.assertTrue(
            any(ticket_2.name in b for b in bodies),
            "Le chatter doit nommer le ticket effectivement ré-ouvert (ticket_2)",
        )

    def test_second_ticket_on_paused_partner_posts_no_rouvert_chatter(self):
        """H1 revue code — création d'un 2ᵉ ticket sur partner déjà paused
        SAV ne doit PAS déclencher un chatter « rouvert » (le ticket est
        neuf, jamais fermé)."""
        schedule = self._create_schedule_direct(self.partner_a)
        ticket_1 = self._make_ticket(self.partner_a)  # paused + chatter suspendu
        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'paused')

        messages_before = len(self.partner_a.message_ids)
        ticket_2 = self._make_ticket(self.partner_a)  # 2ᵉ ticket neuf

        messages_after = list(self.partner_a.message_ids)
        new_messages = messages_after[:len(messages_after) - messages_before]
        bodies = [m.body or '' for m in new_messages]
        self.assertFalse(
            any('rouvert' in b for b in bodies),
            "Aucun chatter « rouvert » attendu — ticket_2 est neuf, pas rouvert",
        )

    def test_write_stage_id_same_value_posts_no_chatter(self):
        """H3 revue code — write({'stage_id': same_id}) sur ticket ouvert
        ne doit poster aucun chatter (idempotence AC10 sur write neutre)."""
        schedule = self._create_schedule_direct(self.partner_a)
        ticket = self._make_ticket(self.partner_a)
        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'paused')

        messages_before = len(self.partner_a.message_ids)
        # Écrire le MÊME stage_id (idempotent, mais présent dans vals)
        ticket.write({'stage_id': ticket.stage_id.id})
        messages_after = len(self.partner_a.message_ids)
        self.assertEqual(
            messages_after, messages_before,
            "Un write neutre de stage_id ne doit poster aucun chatter",
        )

    def test_unlink_last_open_ticket_resumes_schedule(self):
        """M7 revue code — suppression du dernier ticket ouvert d'un partner
        (edge case saisie erronée) → reprise automatique du schedule."""
        schedule = self._create_schedule_direct(self.partner_a)
        ticket = self._make_ticket(self.partner_a)
        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'paused')

        ticket.unlink()
        schedule.invalidate_recordset()
        self.assertEqual(
            schedule.state, 'running',
            "Suppression du dernier ticket ouvert doit reprendre le schedule",
        )

    # ==================================================================
    # AC3 — Recalcul dates à la reprise
    # ==================================================================

    def test_resume_recomputes_planned_dates_for_overdue_lines(self):
        """AC3 — lignes dépassées → today+1, lignes futures inchangées,
        date_planned_original préservé."""
        schedule = self._create_schedule_direct(self.partner_a)
        # 3 lignes avec dates variées, toutes en paused (comme après pause SAV)
        today = fields.Date.today()
        past_date = today - timedelta(days=10)
        near_date = today + timedelta(days=5)
        far_date = today + timedelta(days=60)

        line_past, line_near, line_far = schedule.line_ids[:3]
        original_past = line_past.date_planned_original
        original_near = line_near.date_planned_original
        original_far = line_far.date_planned_original

        line_past.write({'state': 'paused', 'date_planned': past_date})
        line_near.write({'state': 'paused', 'date_planned': near_date})
        line_far.write({'state': 'paused', 'date_planned': far_date})
        schedule.write({
            'state': 'paused',
            'pause_reason': 'sav_open',
            'sav_paused_date': today - timedelta(days=15),
        })

        schedule._resume_from_sav()

        # État
        for line in (line_past, line_near, line_far):
            self.assertEqual(line.state, 'pending')

        self.assertEqual(line_past.date_planned, today + timedelta(days=1))
        self.assertEqual(line_near.date_planned, near_date)
        self.assertEqual(line_far.date_planned, far_date)

        # date_planned_original inchangé
        self.assertEqual(line_past.date_planned_original, original_past)
        self.assertEqual(line_near.date_planned_original, original_near)
        self.assertEqual(line_far.date_planned_original, original_far)

    # ==================================================================
    # AC4 — Multi-schedules d'un même partner
    # ==================================================================

    def test_pause_affects_all_partner_schedules_across_warehouses(self):
        """AC4 — 2 schedules sur 2 boutiques différentes, 1 ticket → les 2 paused."""
        sched_1 = self._create_schedule_direct(self.partner_a, warehouse=self.warehouse)
        sched_2 = self._create_schedule_direct(self.partner_a, warehouse=self.warehouse_2)

        ticket = self._make_ticket(self.partner_a)

        sched_1.invalidate_recordset()
        sched_2.invalidate_recordset()
        self.assertEqual(sched_1.state, 'paused')
        self.assertEqual(sched_2.state, 'paused')

        # Reprise : les 2 basculent aussi
        ticket.write({'stage_id': self.stage_done.id})
        sched_1.invalidate_recordset()
        sched_2.invalidate_recordset()
        self.assertEqual(sched_1.state, 'running')
        self.assertEqual(sched_2.state, 'running')

    # ==================================================================
    # AC9 — Non-régressions cascade opt-out et cron
    # ==================================================================

    def test_optout_cancels_paused_schedule_cleanly(self):
        """AC9 — schedule paused SAV, opt-out → schedule cancelled propre."""
        schedule = self._create_schedule_direct(self.partner_a)
        self._make_ticket(self.partner_a)
        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'paused')

        self.partner_a.write({'optical_followup_optout': True})

        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'cancelled')
        for line in schedule.line_ids:
            self.assertIn(line.state, ('cancelled', 'done', 'skipped'))

    def test_cron_materialize_skips_paused_lines(self):
        """AC9 — cron _run_daily_cron : lignes paused non matérialisées."""
        schedule = self._create_schedule_direct(self.partner_a)
        # Forcer une ligne paused avec date_planned = today + 3
        line = schedule.line_ids[0]
        line.write({
            'state': 'paused',
            'date_planned': fields.Date.add(fields.Date.today(), days=3),
        })
        # Aligner schedule state cohérent avec paused
        schedule.write({
            'state': 'paused',
            'pause_reason': 'sav_open',
            'sav_paused_date': fields.Date.today(),
        })

        self.env['optical.followup.schedule']._run_daily_cron()

        line.invalidate_recordset()
        self.assertFalse(
            line.activity_id,
            "Aucune activité ne doit être créée pour une ligne paused",
        )

    # ==================================================================
    # AC10 — Idempotence
    # ==================================================================

    def test_ticket_write_unrelated_field_is_noop(self):
        """AC10 — write d'un champ neutre (name) : aucune ré-écriture schedule."""
        schedule = self._create_schedule_direct(self.partner_a)
        ticket = self._make_ticket(self.partner_a)
        schedule.invalidate_recordset()
        first_write = schedule.write_date

        # Attendre au minimum 1 microseconde et écrire un champ neutre
        ticket.write({'name': 'Titre renommé'})
        schedule.invalidate_recordset()
        second_write = schedule.write_date

        # Si aucune ré-écriture n'a eu lieu, write_date est strictement inchangé
        self.assertEqual(
            first_write, second_write,
            "Le hook ne doit pas ré-écrire le schedule sur un write neutre",
        )

    # ==================================================================
    # AC8 — Form() helper : vue form schedule + compute duration
    # ==================================================================

    # ==================================================================
    # Story 17-4 AC6 — double-post chatter sur schedule
    # ==================================================================

    def test_sav_pause_posts_chatter_on_schedule(self):
        """Story 17-4 AC6 — création ticket → chatter « suspendu » posté
        SUR le schedule (en plus du partner). Subtype mail.mt_note (L12)
        pour ne pas notifier par email les followers."""
        schedule = self._create_schedule_direct(self.partner_a)
        self._make_ticket(self.partner_a)

        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'paused')
        bodies = schedule.message_ids.mapped('body')
        self.assertTrue(
            any('suspendu' in (b or '').lower() for b in bodies),
            "Le chatter du schedule doit contenir le message 'suspendu'",
        )
        # Subtype mt_note (L12) — les nouveaux messages Story 17-4 ne
        # doivent pas déclencher de notification email.
        mt_note = self.env.ref('mail.mt_note')
        story_msgs = schedule.message_ids.filtered(
            lambda m: 'suspendu' in (m.body or '').lower()
        )
        self.assertTrue(story_msgs)
        for msg in story_msgs:
            self.assertEqual(
                msg.subtype_id, mt_note,
                "Les chatters Story 17-4 doivent utiliser mail.mt_note (L12)",
            )

    def test_sav_reopen_posts_chatter_on_schedule(self):
        """Story 17-4 AC6 (M7 revue) — ré-ouverture ticket clos → chatter
        « rouvert — calendrier maintenu en suspension » posté sur le
        schedule (cas oublié initialement, sans lui trou temporel dans
        le fil du schedule)."""
        schedule = self._create_schedule_direct(self.partner_a)
        # 2 tickets — 1 open (paused), 1 clos initialement
        self._make_ticket(self.partner_a)
        ticket_closed = self._make_ticket(self.partner_a, stage=self.stage_done)
        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'paused')

        # Ré-ouvrir le ticket clos
        ticket_closed.write({'stage_id': self.stage_new.id})

        schedule.invalidate_recordset()
        bodies = schedule.message_ids.mapped('body') or []
        self.assertTrue(
            any('rouvert' in (b or '') for b in bodies),
            "Le chatter du schedule doit contenir le message 'rouvert'",
        )

    def test_sav_resume_posts_chatter_on_schedule(self):
        """Story 17-4 AC6 — reprise (clôture dernier ticket ouvert) →
        chatter « repris automatiquement » posté sur le schedule (en plus
        du partner) avec durée de pause."""
        schedule = self._create_schedule_direct(self.partner_a)
        ticket = self._make_ticket(self.partner_a)
        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'paused')

        ticket.write({'stage_id': self.stage_done.id})

        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'running')
        bodies = schedule.message_ids.mapped('body') or []
        self.assertTrue(
            any('repris' in (b or '').lower() for b in bodies),
            "Le chatter du schedule doit contenir le message 'repris'",
        )

    def test_form_schedule_exposes_sav_fields_with_compute_synced(self):
        """AC8 (Form) — la vue form charge sans erreur, compute
        sav_pause_duration_days est bien synchronisé avec l'état paused SAV
        et retombe à 0 quand on repasse en running."""
        schedule = self._create_schedule_direct(self.partner_a)

        # 1) État running initial : duration = 0
        with Form(schedule.with_user(self.user_manager)) as form:
            self.assertEqual(form.state, 'running')
            self.assertEqual(form.sav_pause_duration_days, 0)

        # 2) Simuler pause SAV depuis 15 j (backend direct — Form() ne peut
        #    écrire dans les Selection/Date readonly par UI, mais le compute
        #    est reactif à l'écriture backend, ce que Form() relit ensuite).
        schedule.write({
            'state': 'paused',
            'pause_reason': 'sav_open',
            'sav_paused_date': fields.Date.today() - timedelta(days=15),
        })
        with Form(schedule.with_user(self.user_manager)) as form:
            self.assertEqual(form.state, 'paused')
            self.assertEqual(form.pause_reason, 'sav_open')
            self.assertEqual(
                form.sav_pause_duration_days, 15,
                "Le compute duration doit refléter today - sav_paused_date",
            )

        # 3) Reprise via _resume_from_sav — la vue form doit refléter running
        #    mais le compute retombe à 0 (hors état paused).
        schedule._resume_from_sav()
        with Form(schedule.with_user(self.user_manager)) as form:
            self.assertEqual(form.state, 'running')
            self.assertEqual(
                form.sav_pause_duration_days, 0,
                "La durée doit retomber à 0 après reprise (compute filtre state==paused)",
            )
            # Audit conservé (D-RESUME-DATE = conservation)
            self.assertTrue(
                form.sav_paused_date,
                "sav_paused_date reste renseigné après reprise (audit)",
            )
