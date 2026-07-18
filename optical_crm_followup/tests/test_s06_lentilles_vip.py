# -*- coding: utf-8 -*-
"""Story 17-1 (migrée Story 18-1) — Preset Lentilles 90 j et tiers clients.

Migrée vers le modèle configurable ``optical.customer.tier`` (Story 18-1) :
la Selection ``standard``/``vip`` est remplacée par un Many2one vers les tiers
``tier_standard`` / ``tier_vip``, l'override booléen par un Many2one, le seuil
système par ``tier_vip.threshold_fcfa``. Les scénarios métier (bascule auto,
override, injection des 2 étapes réservées, robustesse anniversaire absent)
sont préservés à l'identique — garantie d'iso-fonctionnalité AC-7.

Couvre :
- AC-1 : preset Lentilles 90 j livré, sélectionné pour SO contact_lens,
  priorité lentilles > progressive > any, désactivable via active=False
- AC-2 : bascule tier automatique (seuil sur le tier, cumul multi-SO, états
  ignorés, changement de seuil)
- AC-3 : override manuel du tier (manager only, chatter, refus non-manager)
- AC-4 : plan plan_vip_extra réservé au tier VIP (structure, désactivable)
- AC-5 : injection à la matérialisation (prochaine occurrence anniversaire,
  cas jour même, défaut = aucune injection, chatter)
- AC-6 : robustesse anniversaire absent (skip silencieux, M+12 reste créée)
+ non-régressions Std18m / Progressive24m / combinaison VIP × contact_lens.
"""
from datetime import date, timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'optical_crm_followup')
class TestS06LentillesVip(TransactionCase):

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
            'name': 'Boutique S06',
            'code': 'S06',
        })

        cls.user_manager = cls.env['res.users'].with_context(
            no_reset_password=True,
        ).create({
            'name': 'Manager S06',
            'login': 'manager_s06',
            'email': 'manager_s06@test.com',
            'groups_id': [Command.set([cls.group_optical_manager.id] + cls.base_groups)],
            'optical_warehouse_ids': [Command.set([cls.warehouse.id])],
        })
        cls.user_commercial = cls.env['res.users'].with_context(
            no_reset_password=True,
        ).create({
            'name': 'Commercial S06',
            'login': 'commercial_s06',
            'email': 'commercial_s06@test.com',
            'groups_id': [Command.set([cls.group_optical_user.id] + cls.base_groups)],
            'optical_warehouse_ids': [Command.set([cls.warehouse.id])],
        })

        # Tiers configurables (Story 18-1) — seed data.
        cls.tier_standard = cls.env.ref('optical_crm_followup.tier_standard')
        cls.tier_vip = cls.env.ref('optical_crm_followup.tier_vip')
        # Garantir le seuil VIP par défaut (500 000) pour ce suite.
        cls.tier_vip.threshold_fcfa = 500000.0

        # Partners — 4 profils tier × birthdate
        cls.partner_standard = cls.env['res.partner'].create({
            'name': 'Client Standard S06',
            'birthdate': date.today() - timedelta(days=int(30 * 365.25)),
            'optical_followup_consent': True,
        })
        cls.partner_vip_auto = cls.env['res.partner'].create({
            'name': 'Client VIP Auto S06',
            'birthdate': date(1985, 8, 15),
            'optical_followup_consent': True,
        })
        cls.partner_vip_override = cls.env['res.partner'].create({
            'name': 'Client VIP Override S06',
            'birthdate': date(1985, 1, 10),
            'optical_followup_consent': True,
        })
        cls.partner_vip_no_bd = cls.env['res.partner'].create({
            'name': 'Client VIP sans Birthdate',
            'birthdate': False,
            'optical_followup_consent': True,
        })

        # Produits
        cls.product_unifocal = cls.env['product.product'].create({
            'name': 'Verre Unifocal S06',
            'type': 'consu',
            'list_price': 100.0,
        })
        cls.product_unifocal.product_tmpl_id.write({
            'optical_type': 'lens',
            'lens_design': 'single_vision',
        })
        cls.product_progressive = cls.env['product.product'].create({
            'name': 'Verre Progressif S06',
            'type': 'consu',
            'list_price': 200.0,
        })
        cls.product_progressive.product_tmpl_id.write({
            'optical_type': 'lens',
            'lens_design': 'progressive',
        })
        cls.product_contact = cls.env['product.product'].create({
            'name': 'Lentille S06',
            'type': 'consu',
            'list_price': 50.0,
        })
        cls.product_contact.product_tmpl_id.write({
            'optical_type': 'contact_lens',
        })
        # Produits à prix dédiés pour tests VIP-auto. On vide ``taxes_id``
        # à la création pour que ``amount_total`` == ``amount_untaxed``
        # (les taxes company-default fausseraient les seuils).
        def _create_priced_product(name, price):
            p = cls.env['product.product'].create({
                'name': name,
                'type': 'consu',
                'list_price': price,
                'taxes_id': [Command.clear()],
            })
            p.product_tmpl_id.write({
                'optical_type': 'lens',
                'lens_design': 'single_vision',
                'taxes_id': [Command.clear()],
            })
            return p

        cls.product_expensive = _create_priced_product('Produit Cher S06', 600000.0)
        cls.product_200k = _create_priced_product('Produit 200k S06', 200000.0)
        cls.product_250k = _create_priced_product('Produit 250k S06', 250000.0)
        cls.product_100k = _create_priced_product('Produit 100k S06', 100000.0)
        cls.product_500k = _create_priced_product('Produit 500k S06', 500000.0)

        # Presets livrés
        cls.plan_std18m = cls.env.ref('optical_crm_followup.plan_standard_18m')
        cls.plan_progressive_24m = cls.env.ref(
            'optical_crm_followup.plan_progressive_24m',
        )
        cls.plan_lentilles = cls.env.ref(
            'optical_crm_followup.plan_lentilles_90j',
        )
        cls.plan_vip_extra = cls.env.ref(
            'optical_crm_followup.plan_vip_extra',
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_sale_order(self, partner, product=None):
        product = product or self.product_unifocal
        return self.env['sale.order'].create({
            'partner_id': partner.id,
            'user_id': self.user_commercial.id,
            'order_line': [Command.create({
                'product_id': product.id,
                'product_uom_qty': 1,
            })],
        })

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
    # AC-1 — Preset Lentilles 90 j
    # ==================================================================

    def test_ac1_lentilles_preset_installed(self):
        """AC-1.1 — le record data existe avec 2 étapes ordonnées."""
        self.assertTrue(self.plan_lentilles)
        self.assertEqual(self.plan_lentilles.optical_type_trigger, 'lentilles')
        self.assertTrue(self.plan_lentilles.active)
        self.assertEqual(self.plan_lentilles.duration_months, 3)
        self.assertEqual(len(self.plan_lentilles.step_ids), 2)
        steps = self.plan_lentilles.step_ids.sorted('sequence')
        self.assertEqual(steps[0].offset_days, 15)
        self.assertEqual(steps[0].suggested_channel, 'whatsapp')
        self.assertEqual(steps[1].offset_days, 60)
        self.assertEqual(steps[1].suggested_channel, 'whatsapp')

    def test_ac1_lentilles_selected_on_contact_lens_so(self):
        """AC-1.2 — SO avec produit contact_lens → plan_lentilles_90j."""
        so = self._make_sale_order(self.partner_standard, product=self.product_contact)
        self._confirm_and_deliver(so)
        schedule = so.followup_schedule_id
        self.assertTrue(schedule)
        self.assertEqual(schedule.plan_id, self.plan_lentilles)
        self.assertEqual(len(schedule.line_ids), 2)
        lines = schedule.line_ids.sorted('date_planned')
        self.assertEqual(
            lines[0].date_planned,
            fields.Date.add(schedule.delivered_date, days=15),
        )
        self.assertEqual(
            lines[1].date_planned,
            fields.Date.add(schedule.delivered_date, days=60),
        )

    def test_ac1_priority_lentilles_over_progressive(self):
        """AC-1.3 — SO mixte (contact_lens + progressive) → lentilles gagne."""
        so = self.env['sale.order'].create({
            'partner_id': self.partner_standard.id,
            'user_id': self.user_commercial.id,
            'order_line': [
                Command.create({
                    'product_id': self.product_contact.id,
                    'product_uom_qty': 1,
                }),
                Command.create({
                    'product_id': self.product_progressive.id,
                    'product_uom_qty': 1,
                }),
            ],
        })
        self._confirm_and_deliver(so)
        self.assertEqual(so.followup_schedule_id.plan_id, self.plan_lentilles)

    def test_ac1_deactivable_falls_back_to_std18m(self):
        """AC-1.4 — désactivation du preset → SO lentilles retombe sur any."""
        self.plan_lentilles.write({'active': False})
        try:
            so = self._make_sale_order(
                self.partner_standard, product=self.product_contact,
            )
            self._confirm_and_deliver(so)
            self.assertEqual(so.followup_schedule_id.plan_id, self.plan_std18m)
        finally:
            self.plan_lentilles.write({'active': True})

    # ==================================================================
    # AC-2 — Bascule tier automatique
    # ==================================================================

    def test_ac2_auto_vip_on_threshold_crossed(self):
        """AC-2.1 — 1 SO sale > seuil → tier auto = VIP."""
        partner = self.env['res.partner'].create({
            'name': 'Client VIP-2.1',
            'optical_followup_consent': True,
        })
        self.assertEqual(partner.optical_customer_tier_id, self.tier_standard)
        so = self._make_sale_order(partner, product=self.product_expensive)
        so.action_confirm()
        partner.invalidate_recordset(['optical_customer_tier_id'])
        self.assertEqual(partner.optical_customer_tier_id, self.tier_vip)

    def test_ac2_cumul_multiple_so(self):
        """AC-2.2 — cumul de plusieurs SO > seuil → VIP."""
        partner = self.env['res.partner'].create({
            'name': 'Client VIP-2.2',
            'optical_followup_consent': True,
        })
        for product in (self.product_200k, self.product_250k):
            so = self._make_sale_order(partner, product=product)
            so.action_confirm()
        partner.invalidate_recordset(['optical_customer_tier_id'])
        self.assertEqual(partner.optical_customer_tier_id, self.tier_standard)
        so3 = self._make_sale_order(partner, product=self.product_100k)
        so3.action_confirm()
        partner.invalidate_recordset(['optical_customer_tier_id'])
        self.assertEqual(partner.optical_customer_tier_id, self.tier_vip)

    def test_ac2_ignore_draft_and_cancel(self):
        """AC-2.3 — SO en draft/cancel ne comptent PAS dans le cumul."""
        partner = self.env['res.partner'].create({
            'name': 'Client VIP-2.3',
            'optical_followup_consent': True,
        })
        # draft (par défaut sur create — jamais action_confirm)
        self._make_sale_order(partner, product=self.product_expensive)
        # confirmé puis annulé
        so_cancel = self._make_sale_order(partner, product=self.product_expensive)
        so_cancel.action_confirm()
        so_cancel._action_cancel()
        partner.invalidate_recordset(['optical_customer_tier_id'])
        self.assertEqual(partner.optical_customer_tier_id, self.tier_standard)

    def test_ac2_threshold_change_recomputes(self):
        """AC-2.4 — changer le seuil du tier recalcule les partners impactés."""
        partner = self.env['res.partner'].create({
            'name': 'Client VIP-2.4',
            'optical_followup_consent': True,
        })
        so = self._make_sale_order(partner, product=self.product_expensive)
        so.action_confirm()
        partner.invalidate_recordset(['optical_customer_tier_id'])
        self.assertEqual(partner.optical_customer_tier_id, self.tier_vip)
        # Élever le seuil du tier au-delà du cumul (600 000) → repasse standard
        # via le recompute déclenché par le write sur le tier.
        self.tier_vip.threshold_fcfa = 800000.0
        try:
            partner.invalidate_recordset(['optical_customer_tier_id'])
            self.assertEqual(
                partner.optical_customer_tier_id, self.tier_standard,
            )
        finally:
            self.tier_vip.threshold_fcfa = 500000.0

    def test_ac2_default_threshold_500k_boundary(self):
        """AC-2.5 — CA == seuil (500 000) → VIP (comparaison inclusive)."""
        partner = self.env['res.partner'].create({
            'name': 'Client VIP-2.5',
            'optical_followup_consent': True,
        })
        so = self._make_sale_order(partner, product=self.product_500k)
        so.action_confirm()
        partner.invalidate_recordset(['optical_customer_tier_id'])
        self.assertEqual(partner.optical_customer_tier_id, self.tier_vip)

    def test_ac2_cancel_transition_downgrades_to_standard(self):
        """AC-2 — bascule VIP → standard sur cancel de la SO.

        Vérifie la propagation de la dépendance ``sale_order_ids.state`` :
        partner passé VIP par une SO 600k puis cancel → doit repasser standard
        sans intervention manuelle.
        """
        partner = self.env['res.partner'].create({
            'name': 'Client VIP-cancel',
            'optical_followup_consent': True,
        })
        so = self._make_sale_order(partner, product=self.product_expensive)
        so.action_confirm()
        partner.invalidate_recordset(['optical_customer_tier_id'])
        self.assertEqual(partner.optical_customer_tier_id, self.tier_vip)
        so._action_cancel()
        partner.invalidate_recordset(['optical_customer_tier_id'])
        self.assertEqual(partner.optical_customer_tier_id, self.tier_standard)

    # ==================================================================
    # AC-3 — Override manuel du tier
    # ==================================================================

    def test_ac3_manager_can_set_override(self):
        """AC-3.1 — manager peut forcer le tier VIP, effet immédiat."""
        partner = self.env['res.partner'].create({
            'name': 'Client VIP-3.1',
            'optical_followup_consent': True,
        })
        self.assertEqual(partner.optical_customer_tier_id, self.tier_standard)
        partner.with_user(self.user_manager).write({
            'optical_customer_tier_override_id': self.tier_vip.id,
        })
        partner.invalidate_recordset(['optical_customer_tier_id'])
        self.assertEqual(partner.optical_customer_tier_id, self.tier_vip)

    def test_ac3_override_can_be_removed(self):
        """AC-3.1 — retirer l'override → repasse au calcul auto."""
        partner = self.env['res.partner'].create({
            'name': 'Client VIP-3.2',
            'optical_followup_consent': True,
            'optical_customer_tier_override_id': self.tier_vip.id,
        })
        partner.invalidate_recordset(['optical_customer_tier_id'])
        self.assertEqual(partner.optical_customer_tier_id, self.tier_vip)
        partner.with_user(self.user_manager).write({
            'optical_customer_tier_override_id': False,
        })
        partner.invalidate_recordset(['optical_customer_tier_id'])
        self.assertEqual(partner.optical_customer_tier_id, self.tier_standard)

    def test_ac3_non_manager_cannot_set_override(self):
        """AC-3.2 — un commercial ne peut PAS écrire override (AccessError)."""
        partner = self.env['res.partner'].create({
            'name': 'Client VIP-3.3',
            'optical_followup_consent': True,
        })
        with self.assertRaises(AccessError):
            partner.with_user(self.user_commercial).write({
                'optical_customer_tier_override_id': self.tier_vip.id,
            })

    def test_ac3_override_leaves_sale_orders_untouched(self):
        """AC-3 — l'override ne modifie AUCUNE donnée sale.order.

        Le tier est un indicateur CRM, pas un attribut commercial. Écrire
        l'override ne doit ni toucher les lignes SO, ni les montants, ni
        les états.
        """
        partner = self.env['res.partner'].create({
            'name': 'Client VIP-3.4',
            'optical_followup_consent': True,
        })
        so = self._make_sale_order(partner)
        so.action_confirm()
        before = {
            'state': so.state,
            'amount_total': so.amount_total,
            'amount_untaxed': so.amount_untaxed,
            'write_date': so.write_date,
        }
        line_before = {
            l.id: (l.product_uom_qty, l.price_unit, l.price_subtotal)
            for l in so.order_line
        }
        partner.with_user(self.user_manager).write({
            'optical_customer_tier_override_id': self.tier_vip.id,
        })
        so.invalidate_recordset()
        self.assertEqual(so.state, before['state'])
        self.assertEqual(so.amount_total, before['amount_total'])
        self.assertEqual(so.amount_untaxed, before['amount_untaxed'])
        self.assertEqual(so.write_date, before['write_date'])
        for line in so.order_line:
            self.assertEqual(
                (line.product_uom_qty, line.price_unit, line.price_subtotal),
                line_before[line.id],
            )

    def test_ac3_chatter_traces_override_toggle(self):
        """AC-3.3 — chatter partner trace le passage VIP par override."""
        partner = self.env['res.partner'].create({
            'name': 'Client VIP-3.chatter',
            'optical_followup_consent': True,
        })
        before_ids = partner.message_ids.ids
        partner.with_user(self.user_manager).write({
            'optical_customer_tier_override_id': self.tier_vip.id,
        })
        new_messages = partner.message_ids.filtered(
            lambda m: m.id not in before_ids
        )
        bodies = " ".join(new_messages.mapped('body'))
        self.assertIn("VIP", bodies)
        self.assertIn("override", bodies.lower())

    # ==================================================================
    # AC-4 — plan_vip_extra réservé au tier VIP
    # ==================================================================

    def test_ac4_vip_plan_exists_and_configured(self):
        """AC-4.1 — plan_vip_extra existe, réservé au tier VIP, 2 étapes."""
        self.assertTrue(self.plan_vip_extra)
        self.assertEqual(self.plan_vip_extra.sequence, 100)
        self.assertEqual(self.plan_vip_extra.tier_id, self.tier_vip)
        self.assertTrue(self.plan_vip_extra.active)
        self.assertEqual(len(self.plan_vip_extra.step_ids), 2)
        birthday_step = self.plan_vip_extra.step_ids.filtered('birthday_step')
        self.assertEqual(len(birthday_step), 1)
        self.assertEqual(birthday_step.suggested_channel, 'call')
        m12_step = self.plan_vip_extra.step_ids - birthday_step
        self.assertFalse(m12_step.birthday_step)
        self.assertEqual(m12_step.offset_days, 365)
        self.assertEqual(m12_step.suggested_channel, 'email')

    def test_ac4_vip_plan_never_selected_by_fr02(self):
        """AC-4.2 — _select_for_sale_order ne retient JAMAIS un plan réservé."""
        # SO avec produit unifocal → plan any → Standard 18m gagne
        so = self._make_sale_order(self.partner_standard)
        plan = self.env['optical.followup.plan']._select_for_sale_order(so)
        self.assertEqual(plan, self.plan_std18m)

    def test_ac4_deactivating_vip_plan_stops_injection(self):
        """AC-4.2 — désactiver plan_vip_extra → aucune étape réservée injectée."""
        partner = self.env['res.partner'].create({
            'name': 'Client VIP-4.4',
            'optical_followup_consent': True,
            'birthdate': date(1985, 8, 15),
            'optical_customer_tier_override_id': self.tier_vip.id,
        })
        self.plan_vip_extra.write({'active': False})
        try:
            so = self._make_sale_order(partner)
            self._confirm_and_deliver(so)
            schedule = so.followup_schedule_id
            self.assertTrue(schedule)
            # Aucune ligne réservée → seulement les 3 étapes Std18m
            self.assertEqual(len(schedule.line_ids), 3)
        finally:
            self.plan_vip_extra.write({'active': True})

    # ==================================================================
    # AC-5 — Injection à la matérialisation
    # ==================================================================

    def test_ac5_vip_injects_two_lines(self):
        """AC-5.1 — partner VIP → 2 lignes réservées additionnelles injectées."""
        partner = self.env['res.partner'].create({
            'name': 'Client VIP-5.1',
            'optical_followup_consent': True,
            'birthdate': date(1985, 8, 15),
            'optical_customer_tier_override_id': self.tier_vip.id,
        })
        so = self._make_sale_order(partner)  # unifocal → Std18m (3 étapes)
        self._confirm_and_deliver(so)
        schedule = so.followup_schedule_id
        # 3 étapes Std18m + 2 étapes VIP = 5 lignes
        self.assertEqual(len(schedule.line_ids), 5)
        vip_lines = schedule.line_ids.filtered(
            lambda l: l.step_id.plan_id == self.plan_vip_extra
        )
        self.assertEqual(len(vip_lines), 2)

    def test_ac5_next_birthday_direct_helper(self):
        """AC-5.2 — helper _next_birthday_occurrence en direct (déterminisme)."""
        from odoo.addons.optical_crm_followup.models.optical_followup_schedule import (
            _next_birthday_occurrence,
        )
        # Cas A : anniversaire déjà passé cette année → year + 1
        result_a = _next_birthday_occurrence(
            date(1985, 1, 10), date(2026, 7, 20),
        )
        self.assertEqual(result_a, date(2027, 1, 10))
        # Cas B : anniversaire futur cette année → même année
        result_b = _next_birthday_occurrence(
            date(1985, 12, 25), date(2026, 7, 20),
        )
        self.assertEqual(result_b, date(2026, 12, 25))

    def test_ac5_birthday_sameday_pushed_to_next_year(self):
        """AC-5.3 — anniversaire = delivered_date → next year."""
        from odoo.addons.optical_crm_followup.models.optical_followup_schedule import (
            _next_birthday_occurrence,
        )
        ref = date(2026, 7, 20)
        birthdate = date(1985, ref.month, ref.day)
        result = _next_birthday_occurrence(birthdate, ref)
        self.assertEqual(result, date(ref.year + 1, ref.month, ref.day))

    def test_ac5_birthday_leap_year_falls_back_to_28_feb(self):
        """D-VIP-LEAP-YEAR — partner né le 29 février → repli 28-02 en non-bissextile."""
        from odoo.addons.optical_crm_followup.models.optical_followup_schedule import (
            _next_birthday_occurrence,
        )
        result = _next_birthday_occurrence(date(2000, 2, 29), date(2026, 6, 1))
        self.assertEqual(result, date(2027, 2, 28))

    def test_ac5_standard_no_injection(self):
        """AC-5.4 — partner standard → aucune étape réservée injectée."""
        so = self._make_sale_order(self.partner_standard)
        self._confirm_and_deliver(so)
        schedule = so.followup_schedule_id
        self.assertEqual(len(schedule.line_ids), 3)
        vip_lines = schedule.line_ids.filtered(
            lambda l: l.step_id.plan_id == self.plan_vip_extra
        )
        self.assertFalse(vip_lines)

    def test_ac5_chatter_mentions_vip_injection(self):
        """AC-5.5 — chatter partner + schedule mentionne l'injection réservée."""
        partner = self.env['res.partner'].create({
            'name': 'Client VIP-5.5',
            'optical_followup_consent': True,
            'birthdate': date(1985, 8, 15),
            'optical_customer_tier_override_id': self.tier_vip.id,
        })
        so = self._make_sale_order(partner)
        self._confirm_and_deliver(so)
        schedule = so.followup_schedule_id
        partner_bodies = " ".join(partner.message_ids.mapped('body'))
        self.assertIn("VIP", partner_bodies)
        schedule_bodies = " ".join(schedule.message_ids.mapped('body'))
        self.assertIn("VIP", schedule_bodies)

    def test_ac5_vip_plan_missing_graceful(self):
        """AC-5.6 — plan_vip_extra inactif → aucune injection, aucune erreur."""
        self.plan_vip_extra.write({'active': False})
        try:
            partner = self.env['res.partner'].create({
                'name': 'Client VIP-5.6',
                'optical_followup_consent': True,
                'birthdate': date(1985, 8, 15),
                'optical_customer_tier_override_id': self.tier_vip.id,
            })
            so = self._make_sale_order(partner)
            self._confirm_and_deliver(so)  # ne doit PAS lever
            schedule = so.followup_schedule_id
            self.assertEqual(len(schedule.line_ids), 3)
        finally:
            self.plan_vip_extra.write({'active': True})

    # ==================================================================
    # AC-6 — Robustesse anniversaire absent
    # ==================================================================

    def test_ac6_vip_without_birthdate_skips_anniversary_keeps_m12(self):
        """AC-6.1 — partner VIP sans birthdate : anniv skippé, M+12 créée."""
        partner = self.env['res.partner'].create({
            'name': 'Client VIP-6.1',
            'optical_followup_consent': True,
            'birthdate': False,
            'optical_customer_tier_override_id': self.tier_vip.id,
        })
        so = self._make_sale_order(partner)
        self._confirm_and_deliver(so)
        schedule = so.followup_schedule_id
        vip_lines = schedule.line_ids.filtered(
            lambda l: l.step_id.plan_id == self.plan_vip_extra
        )
        self.assertEqual(len(vip_lines), 1)
        self.assertFalse(vip_lines.step_id.birthday_step)
        self.assertEqual(vip_lines.step_id.offset_days, 365)

    def test_ac6_chatter_mentions_skip(self):
        """AC-6.2 — le chatter mentionne l'anniversaire skippé."""
        partner = self.env['res.partner'].create({
            'name': 'Client VIP-6.2',
            'optical_followup_consent': True,
            'birthdate': False,
            'optical_customer_tier_override_id': self.tier_vip.id,
        })
        so = self._make_sale_order(partner)
        self._confirm_and_deliver(so)
        bodies = " ".join(partner.message_ids.mapped('body')).lower()
        self.assertIn("anniversaire", bodies)
        self.assertTrue(
            "skipp" in bodies or "manquante" in bodies or "date de naissance" in bodies,
            "Le chatter partner ne mentionne pas explicitement le skip anniversaire",
        )

    # ==================================================================
    # Non-régressions et interactions
    # ==================================================================

    def test_regression_std18m_unifocal_unchanged(self):
        """Régression S15.2 — SO unifocal partner standard → 3 étapes Std18m intactes."""
        so = self._make_sale_order(self.partner_standard)
        self._confirm_and_deliver(so)
        schedule = so.followup_schedule_id
        self.assertEqual(schedule.plan_id, self.plan_std18m)
        self.assertEqual(len(schedule.line_ids), 3)

    def test_regression_progressive24m_unchanged(self):
        """Régression S16.1 — SO progressive partner standard → 13 étapes Progressive."""
        so = self._make_sale_order(
            self.partner_standard, product=self.product_progressive,
        )
        self._confirm_and_deliver(so)
        schedule = so.followup_schedule_id
        self.assertEqual(schedule.plan_id, self.plan_progressive_24m)
        self.assertEqual(len(schedule.line_ids), 13)

    def test_regression_vip_on_contact_lens_produces_lentilles_plus_vip(self):
        """Combinaison — VIP × contact_lens → Lentilles90j (2) + VIP (2) = 4 lignes."""
        partner = self.env['res.partner'].create({
            'name': 'Client VIP × Lentilles',
            'optical_followup_consent': True,
            'birthdate': date(1985, 8, 15),
            'optical_customer_tier_override_id': self.tier_vip.id,
        })
        so = self._make_sale_order(partner, product=self.product_contact)
        self._confirm_and_deliver(so)
        schedule = so.followup_schedule_id
        self.assertEqual(schedule.plan_id, self.plan_lentilles)
        # 2 Lentilles + 2 VIP = 4 lignes au total
        self.assertEqual(len(schedule.line_ids), 4)

    def test_anonymized_partner_resets_override(self):
        """S17-3 × S18-1 — l'anonymisation reset optical_customer_tier_override_id."""
        partner = self.env['res.partner'].create({
            'name': 'Client anonymisable',
            'optical_followup_consent': True,
            'optical_customer_tier_override_id': self.tier_vip.id,
        })
        self.assertTrue(partner.optical_customer_tier_override_id)
        partner._anonymize_for_followup(reason='inactive_5y')
        self.assertFalse(partner.optical_customer_tier_override_id)
        self.assertTrue(partner.optical_anonymized)

    # ==================================================================
    # Cross-check S16.2 SAV pause / réachat
    # ==================================================================

    def test_regression_sav_pauses_vip_lines(self):
        """Pause SAV met les lignes réservées en 'paused' comme les autres."""
        partner = self.env['res.partner'].create({
            'name': 'Client VIP + SAV',
            'optical_followup_consent': True,
            'birthdate': date(1985, 8, 15),
            'optical_customer_tier_override_id': self.tier_vip.id,
        })
        so = self._make_sale_order(partner)
        self._confirm_and_deliver(so)
        schedule = so.followup_schedule_id
        vip_lines = schedule.line_ids.filtered(
            lambda l: l.step_id.plan_id == self.plan_vip_extra
        )
        self.assertEqual(len(vip_lines), 2)
        self.env['helpdesk.ticket'].create({
            'name': 'Ticket SAV VIP',
            'description': '<p>SAV VIP test</p>',
            'partner_id': partner.id,
            'stage_id': self.env.ref(
                'helpdesk_mgmt.helpdesk_ticket_stage_new',
            ).id,
        })
        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'paused')
        vip_lines_after = schedule.line_ids.filtered(
            lambda l: l.step_id.plan_id == self.plan_vip_extra
        )
        self.assertTrue(
            all(l.state == 'paused' for l in vip_lines_after),
            "Les lignes réservées doivent passer en paused avec le schedule",
        )

    def test_regression_reachat_reinjects_vip(self):
        """Réachat d'un partner VIP → nouveau schedule ré-injecte les étapes."""
        partner = self.env['res.partner'].create({
            'name': 'Client VIP réachat',
            'optical_followup_consent': True,
            'birthdate': date(1985, 8, 15),
            'optical_customer_tier_override_id': self.tier_vip.id,
        })
        so1 = self._make_sale_order(partner)
        self._confirm_and_deliver(so1)
        schedule1 = so1.followup_schedule_id
        self.assertEqual(len(schedule1.line_ids), 5)  # 3 Std18m + 2 VIP
        so2 = self._make_sale_order(partner)
        self._confirm_and_deliver(so2)
        schedule2 = so2.followup_schedule_id
        self.assertNotEqual(schedule1.id, schedule2.id)
        schedule1.invalidate_recordset()
        self.assertEqual(schedule1.state, 'fulfilled')
        vip_lines_new = schedule2.line_ids.filtered(
            lambda l: l.step_id.plan_id == self.plan_vip_extra
        )
        self.assertEqual(len(vip_lines_new), 2)
