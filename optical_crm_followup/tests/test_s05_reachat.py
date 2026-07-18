# -*- coding: utf-8 -*-
"""Story 16.2 — Réachat anticipé : validation périmètre S15.2 + cas croisé SAV
+ preset-cross (D4 rétro) + non-régression paused non-SAV."""
from datetime import date, timedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'optical_crm_followup')
class TestS05Reachat(TransactionCase):

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
            'name': 'Boutique S05',
            'code': 'S05',
        })
        cls.warehouse_other = cls.env['stock.warehouse'].create({
            'name': 'Boutique S05-B',
            'code': 'S05B',
        })

        cls.user_referent = cls.env['res.users'].with_context(
            no_reset_password=True
        ).create({
            'name': 'Commercial S05',
            'login': 'commercial_s05',
            'email': 'commercial_s05@test.com',
            'groups_id': [Command.set([cls.group_optical_user.id] + cls.base_groups)],
            'optical_warehouse_ids': [Command.set([cls.warehouse.id, cls.warehouse_other.id])],
        })

        cls.partner = cls.env['res.partner'].create({
            'name': 'Client Réachat',
            'birthdate': date.today() - timedelta(days=int(30 * 365.25)),
            'email': 'reachat@test.com',
        })
        cls.partner.write({'optical_followup_consent': True})

        # Produits — unifocal (fallback any) et progressive (S16.1 preset)
        cls.product_unifocal = cls.env['product.product'].create({
            'name': 'Verre Unifocal S05',
            'type': 'consu',
            'list_price': 100.0,
        })
        cls.product_unifocal.product_tmpl_id.write({
            'optical_type': 'lens',
            'lens_design': 'single_vision',
        })
        cls.product_progressive = cls.env['product.product'].create({
            'name': 'Verre Progressif S05',
            'type': 'consu',
            'list_price': 200.0,
        })
        cls.product_progressive.product_tmpl_id.write({
            'optical_type': 'lens',
            'lens_design': 'progressive',
        })

        cls.plan_std18m = cls.env.ref('optical_crm_followup.plan_standard_18m')
        cls.plan_progressive_24m = cls.env.ref(
            'optical_crm_followup.plan_progressive_24m'
        )
        cls.stage_new = cls.env.ref('helpdesk_mgmt.helpdesk_ticket_stage_new')

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_sale_order(self, product, warehouse=None):
        vals = {
            'partner_id': self.partner.id,
            'user_id': self.user_referent.id,
            'order_line': [Command.create({
                'product_id': product.id,
                'product_uom_qty': 1,
            })],
        }
        if warehouse:
            vals['warehouse_id'] = warehouse.id
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

    # ==================================================================
    # AC5 — Réachat happy path (validation S15.2 conservé)
    # ==================================================================

    def test_reachat_same_warehouse_fulfills_and_creates_new(self):
        """AC5 — 2ᵉ picking même warehouse : old fulfilled + new running."""
        so_1 = self._make_sale_order(self.product_unifocal, self.warehouse)
        self._confirm_and_deliver(so_1)
        sched_1 = so_1.followup_schedule_id
        self.assertTrue(sched_1)
        self.assertEqual(sched_1.state, 'running')

        so_2 = self._make_sale_order(self.product_unifocal, self.warehouse)
        self._confirm_and_deliver(so_2)

        sched_1.invalidate_recordset()
        self.assertEqual(sched_1.state, 'fulfilled')
        cancelled = sched_1.line_ids.filtered(lambda l: l.state == 'cancelled')
        self.assertTrue(cancelled)
        for line in cancelled:
            self.assertIn("Réachat anticipé", line.outcome_note or '')

        new_sched = so_2.followup_schedule_id
        self.assertTrue(new_sched)
        self.assertNotEqual(new_sched.id, sched_1.id)
        self.assertEqual(new_sched.state, 'running')

    # ==================================================================
    # AC5 — Scope warehouse (D-SCOPE = A partner+warehouse)
    # ==================================================================

    def test_reachat_other_warehouse_does_not_close_first_schedule(self):
        """AC5 D-SCOPE — 2ᵉ picking autre warehouse : 2ᵉ schedule indépendant."""
        so_1 = self._make_sale_order(self.product_unifocal, self.warehouse)
        self._confirm_and_deliver(so_1)
        sched_1 = so_1.followup_schedule_id

        so_2 = self._make_sale_order(self.product_unifocal, self.warehouse_other)
        self._confirm_and_deliver(so_2)

        sched_1.invalidate_recordset()
        self.assertEqual(
            sched_1.state, 'running',
            "Warehouse d'origine doit rester actif (D-SCOPE = A)",
        )
        sched_2 = so_2.followup_schedule_id
        self.assertTrue(sched_2)
        self.assertNotEqual(sched_2, sched_1)
        self.assertEqual(sched_2.warehouse_id, self.warehouse_other)

    # ==================================================================
    # AC6 — Cas croisé réachat pendant SAV
    # ==================================================================

    def test_reachat_during_sav_creates_new_paused_immediately(self):
        """AC6 — schedule paused SAV, nouveau picking → new schedule
        immédiatement re-paused, chatter unifié posté."""
        # 1er cycle : créer schedule + mettre en pause SAV via ticket
        so_1 = self._make_sale_order(self.product_unifocal, self.warehouse)
        self._confirm_and_deliver(so_1)
        sched_1 = so_1.followup_schedule_id
        ticket = self.env['helpdesk.ticket'].create({
            'name': 'Ticket SAV réachat',
            'description': '<p>Test</p>',
            'partner_id': self.partner.id,
            'stage_id': self.stage_new.id,
        })
        sched_1.invalidate_recordset()
        self.assertEqual(sched_1.state, 'paused')
        self.assertEqual(sched_1.pause_reason, 'sav_open')

        # 2ᵉ picking dans la même warehouse
        so_2 = self._make_sale_order(self.product_unifocal, self.warehouse)
        self._confirm_and_deliver(so_2)

        # Ancien schedule fulfilled + lignes paused → cancelled
        sched_1.invalidate_recordset()
        self.assertEqual(sched_1.state, 'fulfilled')
        cancelled = sched_1.line_ids.filtered(lambda l: l.state == 'cancelled')
        self.assertTrue(cancelled, "Les lignes paused doivent aussi être annulées")

        # Nouveau schedule immédiatement paused (ticket toujours ouvert)
        sched_2 = so_2.followup_schedule_id
        self.assertTrue(sched_2)
        self.assertEqual(sched_2.state, 'paused')
        self.assertEqual(sched_2.pause_reason, 'sav_open')

        # Chatter unifié posté sur le partner
        bodies = self.partner.message_ids.mapped('body')
        self.assertTrue(
            any('pendant SAV' in (b or '') for b in bodies),
            "Un chatter unifié 'pendant SAV' doit avoir été posté",
        )

        # D-CROSS-SAV-CHATTER : verrouiller l'absence de chatters granulaires
        # sur le NOUVEAU schedule (skip_chatter=True doit muter la pause).
        # On compte les messages postés APRÈS la création du 2ᵉ SO — il ne
        # doit y avoir qu'un seul chatter unifié « pendant SAV », pas de
        # « suspendu automatiquement » redondant pour sched_2.
        new_bodies = [b or '' for b in bodies]
        suspendu_count = sum(
            1 for b in new_bodies
            if 'suspendu automatiquement' in b and sched_2.name in b
        )
        self.assertEqual(
            suspendu_count, 0,
            "Aucun chatter 'suspendu automatiquement' redondant sur le "
            "nouveau schedule — le chatter unifié doit suffire",
        )

        # Ticket toujours cohérent
        self.assertFalse(ticket.closed)

    # ==================================================================
    # AC7 — Réachat preset-cross (D4 rétro)
    # ==================================================================

    def test_reachat_std18m_to_progressive24m(self):
        """AC7 — old Std 18m → new Progressifs 24m par preset-cross naturel."""
        so_1 = self._make_sale_order(self.product_unifocal, self.warehouse)
        self._confirm_and_deliver(so_1)
        sched_1 = so_1.followup_schedule_id
        self.assertEqual(sched_1.plan_id, self.plan_std18m)

        so_2 = self._make_sale_order(self.product_progressive, self.warehouse)
        self._confirm_and_deliver(so_2)

        sched_1.invalidate_recordset()
        self.assertEqual(sched_1.state, 'fulfilled')

        sched_2 = so_2.followup_schedule_id
        self.assertTrue(sched_2)
        self.assertEqual(sched_2.plan_id, self.plan_progressive_24m)
        self.assertEqual(
            len(sched_2.line_ids), 13,
            "Le preset Progressifs 24m livre 13 étapes",
        )

    # ==================================================================
    # Non-régression S15.2 — schedule paused motif manuel
    # ==================================================================

    # ==================================================================
    # Story 17-4 AC6 — double-post chatter sur schedule au réachat
    # ==================================================================

    def test_reachat_posts_chatter_on_new_schedule(self):
        """Story 17-4 AC6 — le nouveau schedule créé par
        _create_from_picking reçoit un chatter « Calendrier de fidélisation
        démarré ». L'ancien (fulfilled) n'a rien à ajouter."""
        so_1 = self._make_sale_order(self.product_unifocal, self.warehouse)
        self._confirm_and_deliver(so_1)
        sched_1 = so_1.followup_schedule_id
        bodies_new = sched_1.message_ids.mapped('body') or []
        self.assertTrue(
            any('démarré' in (b or '').lower() for b in bodies_new),
            "Le chatter du nouveau schedule doit contenir 'démarré'",
        )

    def test_reachat_cross_sav_posts_unified_chatter_on_schedule(self):
        """Story 17-4 AC6 (D-CROSS-SAV-CHATTER) — le message unifié
        « Réachat anticipé pendant SAV en cours … » est aussi posté sur
        le nouveau schedule (en plus du partner)."""
        so_1 = self._make_sale_order(self.product_unifocal, self.warehouse)
        self._confirm_and_deliver(so_1)
        # Pause SAV
        self.env['helpdesk.ticket'].create({
            'name': 'Ticket SAV cross',
            'description': '<p>Test</p>',
            'partner_id': self.partner.id,
            'stage_id': self.stage_new.id,
        })
        sched_1 = so_1.followup_schedule_id
        sched_1.invalidate_recordset()
        self.assertEqual(sched_1.state, 'paused')

        # 2ᵉ picking pendant SAV
        so_2 = self._make_sale_order(self.product_unifocal, self.warehouse)
        self._confirm_and_deliver(so_2)
        sched_2 = so_2.followup_schedule_id

        bodies_sched_2 = sched_2.message_ids.mapped('body') or []
        self.assertTrue(
            any('pendant SAV' in (b or '') for b in bodies_sched_2),
            "Le chatter unifié 'pendant SAV' doit être posté sur le "
            "nouveau schedule (AC6 D-CROSS-SAV-CHATTER)",
        )

    def test_reachat_paused_manual_state_is_also_fulfilled(self):
        """T4.1 — filtre state in (running, paused) : même comportement
        pour pause_reason='manual' que pour 'sav_open'."""
        so_1 = self._make_sale_order(self.product_unifocal, self.warehouse)
        self._confirm_and_deliver(so_1)
        sched_1 = so_1.followup_schedule_id

        # Passer manuellement en paused (pause_reason='manual')
        sched_1.write({'state': 'paused', 'pause_reason': 'manual'})

        so_2 = self._make_sale_order(self.product_unifocal, self.warehouse)
        self._confirm_and_deliver(so_2)

        sched_1.invalidate_recordset()
        self.assertEqual(
            sched_1.state, 'fulfilled',
            "Un schedule paused manuel doit aussi être clôturé au réachat",
        )
        sched_2 = so_2.followup_schedule_id
        self.assertTrue(sched_2)
        self.assertEqual(sched_2.state, 'running')
