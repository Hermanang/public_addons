# -*- coding: utf-8 -*-
"""Story 17-4 — Refonte UX navigation quotidienne :
- AC1 vue calendar sur schedule.line (color=state_color, H4 revue)
- AC2 vue kanban schedule (records_draggable=0, H5 revue)
- AC3 form enrichie (statusbar, ribbon, smart button, chatter)
- AC4 action_open_lines
- AC5 décorations tree
- AC7 sécurité chatter multi-boutique (H7 revue)
"""
from datetime import date, timedelta

from lxml import etree

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install', 'optical_crm_followup')
class TestS10UxNavigation(TransactionCase):

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

        cls.warehouse_vdn = cls.env['stock.warehouse'].create({
            'name': 'Boutique S10 VDN',
            'code': 'S10V',
        })
        cls.warehouse_corniche = cls.env['stock.warehouse'].create({
            'name': 'Boutique S10 Corniche',
            'code': 'S10C',
        })

        cls.user_vdn = cls.env['res.users'].with_context(
            no_reset_password=True
        ).create({
            'name': 'Commercial VDN S10',
            'login': 'commercial_vdn_s10',
            'email': 'commercial_vdn_s10@test.com',
            'groups_id': [Command.set([cls.group_optical_user.id] + cls.base_groups)],
            'optical_warehouse_ids': [Command.set([cls.warehouse_vdn.id])],
        })
        cls.user_manager = cls.env['res.users'].with_context(
            no_reset_password=True
        ).create({
            'name': 'Manager S10',
            'login': 'manager_s10',
            'email': 'manager_s10@test.com',
            'groups_id': [Command.set([cls.group_optical_manager.id] + cls.base_groups)],
        })

        cls.partner_vdn = cls.env['res.partner'].create({
            'name': 'Client VDN S10',
            'birthdate': date.today() - timedelta(days=int(30 * 365.25)),
            'email': 'client_vdn_s10@test.com',
        })
        cls.partner_vdn.write({'optical_followup_consent': True})
        cls.partner_corniche = cls.env['res.partner'].create({
            'name': 'Client Corniche S10',
            'birthdate': date.today() - timedelta(days=int(30 * 365.25)),
            'email': 'client_corniche_s10@test.com',
        })
        cls.partner_corniche.write({'optical_followup_consent': True})

        cls.plan_std18m = cls.env.ref('optical_crm_followup.plan_standard_18m')

    def _create_schedule_direct(self, partner, warehouse):
        delivered_date = fields.Date.today()
        schedule = self.env['optical.followup.schedule'].create({
            'name': 'SCH-S10-%s-%s' % (partner.id, warehouse.id),
            'partner_id': partner.id,
            'warehouse_id': warehouse.id,
            'plan_id': self.plan_std18m.id,
            'referent_user_id': self.user_manager.id,
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

    # ==================================================================
    # AC2 — Kanban schedule
    # ==================================================================

    def test_schedule_kanban_view_loads(self):
        """AC2 smoke — la vue kanban schedule existe et est chargeable."""
        view = self.env.ref(
            'optical_crm_followup.view_optical_followup_schedule_kanban'
        )
        self.assertEqual(view.model, 'optical.followup.schedule')
        self.assertEqual(view.type, 'kanban')

        # Créer 2 schedules et lire les champs kanban → aucune exception
        self._create_schedule_direct(self.partner_vdn, self.warehouse_vdn)
        self._create_schedule_direct(self.partner_corniche, self.warehouse_corniche)
        Schedule = self.env['optical.followup.schedule']
        records = Schedule.search([]).read([
            'state', 'partner_id', 'warehouse_id', 'referent_user_id',
            'delivered_date', 'next_step_date',
            'steps_total_count', 'steps_done_count',
        ])
        self.assertTrue(records)

    def test_kanban_records_draggable_disabled(self):
        """H5 revue — records_draggable=0 sur la kanban pour empêcher le
        bypass state machine (drag manuel qui contournerait _pause_for_sav,
        _resume_from_sav, action_cancel_for_optout, _create_from_picking).
        Garde-fou contre régression future qui retirerait cet attribut.
        """
        view = self.env.ref(
            'optical_crm_followup.view_optical_followup_schedule_kanban'
        )
        arch = etree.fromstring(view.arch)
        kanban = arch if arch.tag == 'kanban' else arch.find('.//kanban')
        self.assertIsNotNone(kanban, "La vue racine doit être <kanban>")
        self.assertEqual(
            kanban.get('records_draggable'), '0',
            "records_draggable='0' est requis (H5 revue) — la state machine "
            "est gouvernée par les hooks métier, pas par un drag UI",
        )

    # ==================================================================
    # AC1 — Calendar line
    # ==================================================================

    def test_schedule_line_calendar_view_loads(self):
        """AC1 smoke — vue calendar line chargeable + color=state_color."""
        view = self.env.ref(
            'optical_crm_followup.view_optical_followup_schedule_line_calendar'
        )
        self.assertEqual(view.model, 'optical.followup.schedule.line')
        self.assertEqual(view.type, 'calendar')
        arch = etree.fromstring(view.arch)
        calendar = arch if arch.tag == 'calendar' else arch.find('.//calendar')
        self.assertIsNotNone(calendar)
        self.assertEqual(
            calendar.get('color'), 'state_color',
            "color='state_color' est requis (H4 revue) — NE PAS utiliser "
            "color='state', Odoo hasherait les valeurs Selection",
        )
        self.assertEqual(calendar.get('date_start'), 'date_planned')

    def test_state_color_mapping_is_semantic(self):
        """AC1 (H4) — mapping sémantique déterministe entre state et couleur."""
        schedule = self._create_schedule_direct(self.partner_vdn, self.warehouse_vdn)
        line = schedule.line_ids[0]
        expected = {
            'pending': 4,     # bleu
            'overdue': 1,     # rouge
            'done': 10,       # vert
            'cancelled': 2,   # orange
            'skipped': 8,     # gris
            'paused': 3,      # jaune
        }
        for state, color in expected.items():
            line.state = state
            line.invalidate_recordset(['state_color'])
            self.assertEqual(
                line.state_color, color,
                "Mapping state_color[%s] doit être %s" % (state, color),
            )

    # ==================================================================
    # AC3 — Form enrichie
    # ==================================================================

    def test_schedule_form_with_chatter_and_smart_button(self):
        """AC3/AC4 (M9 revue) — la form charge, les computes sont corrects,
        Form() valide l'ARCH XML. Séquence : invalidate → assertions
        compute AVANT Form(), puis Form() pour l'arch."""
        schedule = self._create_schedule_direct(self.partner_vdn, self.warehouse_vdn)
        # 2 lignes done (parmi les N étapes du plan Std 18m — au moins 3
        # étapes pour que next_step_date reste renseigné après ce marquage).
        for line in schedule.line_ids[:2]:
            line.state = 'done'

        # Étape 1 : validations compute
        schedule.invalidate_recordset([
            'steps_total_count', 'steps_done_count', 'next_step_date',
        ])
        self.assertEqual(
            schedule.steps_total_count, len(schedule.line_ids),
            "steps_total_count doit refléter len(line_ids)",
        )
        self.assertEqual(schedule.steps_done_count, 2)
        self.assertTrue(
            schedule.next_step_date,
            "Il reste au moins une ligne pending → next_step_date renseigné",
        )

        # Étape 2 : Form() valide l'ARCH (chatter, smart button, statusbar, ribbon)
        with Form(schedule.with_user(self.user_manager)) as form:
            self.assertEqual(form.state, 'running')

    def test_form_smart_button_hidden_without_plan(self):
        """AC4 (L5) — schedule edge sans plan → steps_total_count == 0 →
        smart button caché via invisible='steps_total_count == 0'.

        Vérifie DEUX niveaux (code review M3) :
          1. Le compute renvoie bien 0 étapes.
          2. L'ARCH XML porte bien l'attribut ``invisible`` sur le bouton —
             garde-fou contre une régression future qui supprimerait
             l'attribut, laissant afficher un « 0/0 étapes » confus.
        """
        edge_schedule = self.env['optical.followup.schedule'].create({
            'name': 'SCH-S10-EDGE',
            'partner_id': self.partner_vdn.id,
            'warehouse_id': self.warehouse_vdn.id,
            'delivered_date': fields.Date.today(),
            'state': 'running',
            # pas de plan_id, pas de lignes
        })
        edge_schedule.invalidate_recordset(['steps_total_count'])
        self.assertEqual(edge_schedule.steps_total_count, 0)
        # La form s'ouvre sans erreur (le bouton est masqué mais présent)
        with Form(edge_schedule.with_user(self.user_manager)) as form:
            self.assertEqual(form.state, 'running')

        # Assertion arch : le bouton porte bien invisible='steps_total_count == 0'
        view = self.env.ref(
            'optical_crm_followup.view_optical_followup_schedule_form'
        )
        arch = etree.fromstring(view.arch)
        buttons = arch.xpath("//button[@name='action_open_lines']")
        self.assertEqual(
            len(buttons), 1,
            "La form doit contenir un unique bouton action_open_lines",
        )
        self.assertEqual(
            buttons[0].get('invisible'), 'steps_total_count == 0',
            "L5 revue : le smart button doit porter "
            "invisible='steps_total_count == 0' pour cacher un affichage "
            "« 0/0 étapes » confus sur les schedules sans plan",
        )

    # ==================================================================
    # AC4 — Action open_lines
    # ==================================================================

    def test_action_open_lines_returns_valid_dict(self):
        """AC4 (H6) — action_open_lines renvoie view_mode='list,form' — PAS
        de 'calendar' car un schedule 13 étapes sur 730 j n'a aucune
        valeur en vue month (masquerait 22/24 mois)."""
        schedule = self._create_schedule_direct(self.partner_vdn, self.warehouse_vdn)
        action = schedule.action_open_lines()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'optical.followup.schedule.line')
        self.assertEqual(action['view_mode'], 'list,form')
        self.assertNotIn('calendar', action['view_mode'])
        self.assertEqual(action['domain'], [('schedule_id', '=', schedule.id)])
        self.assertEqual(action['context']['default_schedule_id'], schedule.id)

    # ==================================================================
    # AC5 — Décorations list
    # ==================================================================

    def test_schedule_tree_has_line_decorations(self):
        """AC5 (L9) — décorations decoration-* présentes sur la vue list
        schedule (M3 : décoration ligne uniquement, pas de widget badge)."""
        view = self.env.ref(
            'optical_crm_followup.view_optical_followup_schedule_tree'
        )
        arch = etree.fromstring(view.arch)
        list_el = arch if arch.tag == 'list' else arch.find('.//list')
        self.assertIsNotNone(list_el)
        expected_decorations = [
            ('decoration-warning', "state == 'paused'"),
            ('decoration-danger', "state == 'cancelled'"),
            ('decoration-muted', "state == 'expired'"),
            ('decoration-success', "state == 'fulfilled'"),
        ]
        for attr, expected in expected_decorations:
            self.assertEqual(
                list_el.get(attr), expected,
                "Attribut %s='%s' attendu sur <list>" % (attr, expected),
            )

    # ==================================================================
    # AC7 — Sécurité chatter multi-boutique (H7 revue)
    # ==================================================================

    def test_schedule_chatter_respects_warehouse_rules(self):
        """H7 revue — ajouter mail.thread sur schedule ne doit PAS créer
        un canal de fuite inter-boutique via l'agrégat message_ids /
        message_follower_ids. Le user VDN ne doit pas pouvoir lire les
        messages d'un schedule Corniche."""
        schedule_corniche = self._create_schedule_direct(
            self.partner_corniche, self.warehouse_corniche,
        )
        # Poster un message via sudo pour bypasser les ACLs à l'écriture
        schedule_corniche.sudo().message_post(
            body="Message confidentiel Corniche",
            subtype_xmlid='mail.mt_note',
        )
        # Le user VDN ne doit pas pouvoir lire ce schedule
        with self.assertRaises(AccessError):
            self.env['optical.followup.schedule'].with_user(
                self.user_vdn,
            ).browse(schedule_corniche.id).read(['message_ids'])
