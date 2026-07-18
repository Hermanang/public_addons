# -*- coding: utf-8 -*-
"""Story 18-1 — Tiers clients configurables (refonte VIP en modèle paramétrable).

Couvre :
- AC-1 : modèle optical.customer.tier (seed, contrainte is_default unique,
  création d'un 3ᵉ tier sans upgrade, ondelete restrict)
- AC-2 : calcul N tiers (seuils croissants), batch, recompute sur seuil
- AC-3 : override M2O (forcer un tier précis) + garde-fou non-manager
- AC-4 : injection cumulative (un Gold reçoit aussi les étapes réservées VIP)
- AC-5 : robustesse seuil non-défaut <= 0 (ignoré)
- AC-6 : migration V1 → 18-1 (mapping partners/override/plan/seuil) + idempotence
"""
import importlib.util
import os
from datetime import date

import psycopg2

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


def _load_migration(filename):
    """Charge un script de migration (nom à tiret) par chemin de fichier."""
    from odoo.addons import optical_crm_followup
    base = os.path.dirname(optical_crm_followup.__file__)
    path = os.path.join(base, 'migrations', '18.0.1.7.0', filename)
    spec = importlib.util.spec_from_file_location(
        'optcrm_mig_' + filename.replace('-', '_').replace('.py', ''), path,
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@tagged('post_install', '-at_install', 'optical_crm_followup')
class TestS18TiersConfigurables(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Tier = cls.env['optical.customer.tier']
        cls.tier_standard = cls.env.ref('optical_crm_followup.tier_standard')
        cls.tier_vip = cls.env.ref('optical_crm_followup.tier_vip')
        cls.tier_vip.threshold_fcfa = 500000.0
        cls.plan_std18m = cls.env.ref('optical_crm_followup.plan_standard_18m')
        cls.plan_vip_extra = cls.env.ref('optical_crm_followup.plan_vip_extra')

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
            'name': 'Boutique S18', 'code': 'S18',
        })
        cls.user_manager = cls.env['res.users'].with_context(
            no_reset_password=True,
        ).create({
            'name': 'Manager S18', 'login': 'manager_s18',
            'email': 'manager_s18@test.com',
            'groups_id': [Command.set([cls.group_optical_manager.id] + cls.base_groups)],
            'optical_warehouse_ids': [Command.set([cls.warehouse.id])],
        })
        cls.user_commercial = cls.env['res.users'].with_context(
            no_reset_password=True,
        ).create({
            'name': 'Commercial S18', 'login': 'commercial_s18',
            'email': 'commercial_s18@test.com',
            'groups_id': [Command.set([cls.group_optical_user.id] + cls.base_groups)],
            'optical_warehouse_ids': [Command.set([cls.warehouse.id])],
        })

        def _priced(name, price):
            p = cls.env['product.product'].create({
                'name': name, 'type': 'consu', 'list_price': price,
                'taxes_id': [Command.clear()],
            })
            p.product_tmpl_id.write({
                'optical_type': 'lens', 'lens_design': 'single_vision',
                'taxes_id': [Command.clear()],
            })
            return p

        cls.product_100k = _priced('P100k S18', 100000.0)
        cls.product_600k = _priced('P600k S18', 600000.0)
        cls.product_2m = _priced('P2M S18', 2000000.0)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _confirmed_so(self, partner, product):
        so = self.env['sale.order'].create({
            'partner_id': partner.id,
            'user_id': self.user_commercial.id,
            'order_line': [Command.create({
                'product_id': product.id, 'product_uom_qty': 1,
            })],
        })
        so.action_confirm()
        return so

    def _deliver(self, partner, product):
        so = self.env['sale.order'].create({
            'partner_id': partner.id,
            'user_id': self.user_commercial.id,
            'order_line': [Command.create({
                'product_id': product.id, 'product_uom_qty': 1,
            })],
        })
        so.action_confirm()
        for picking in so.picking_ids.filtered(
            lambda p: p.picking_type_id.code == 'outgoing'
        ):
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
            picking.button_validate()
        return so

    # ==================================================================
    # AC-1 — Modèle & contraintes
    # ==================================================================

    def test_ac1_seed_tiers(self):
        """AC-1.5 — les 2 tiers seed existent avec les bons attributs."""
        self.assertTrue(self.tier_standard.is_default)
        self.assertEqual(self.tier_standard.code, 'standard')
        self.assertEqual(self.tier_standard.threshold_fcfa, 0.0)
        self.assertFalse(self.tier_vip.is_default)
        self.assertEqual(self.tier_vip.code, 'vip')
        self.assertGreater(self.tier_vip.sequence, self.tier_standard.sequence)

    def test_ac1_single_default_constraint_blocks_two(self):
        """AC-1.3 — impossible d'avoir 2 tiers par défaut."""
        with self.assertRaises(ValidationError):
            self.Tier.create({
                'name': 'Autre défaut', 'is_default': True, 'sequence': 20,
            })

    def test_ac1_cannot_remove_last_default(self):
        """AC-1.3 — impossible de retirer le dernier tier par défaut."""
        with self.assertRaises(ValidationError):
            self.tier_standard.is_default = False

    def test_ac1_action_set_as_default_switches(self):
        """AC-1.3 (revue M2) — bascule atomique du défaut via l'action.

        La contrainte stricte interdit toujours 2 défauts en écriture directe,
        mais ``action_set_as_default`` permet de changer le défaut en un geste.
        """
        gold = self.Tier.create({
            'name': 'Gold', 'code': 'gold', 'sequence': 150,
            'threshold_fcfa': 1500000.0,
        })
        gold.action_set_as_default()
        self.assertTrue(gold.is_default)
        self.assertFalse(self.tier_standard.is_default)
        # Invariant conservé : exactement 1 défaut actif.
        self.assertEqual(
            self.Tier.search_count(
                [('is_default', '=', True), ('active', '=', True)],
            ),
            1,
        )

    def test_ac1_direct_second_default_still_raises(self):
        """AC-1.3 (revue M2) — l'écriture directe d'un 2ᵉ défaut lève toujours.

        Le basculement atomique ne doit PAS relâcher la contrainte hors du
        contexte dédié : poser ``is_default=True`` sur un tier sans passer par
        l'action reste refusé.
        """
        gold = self.Tier.create({
            'name': 'Gold', 'code': 'gold', 'sequence': 150,
            'threshold_fcfa': 1500000.0,
        })
        with self.assertRaises(ValidationError):
            gold.is_default = True

    def test_ac1_create_third_tier_participates(self):
        """AC-1.2 — un 3ᵉ tier créé en UI devient éligible à la bascule."""
        gold = self.Tier.create({
            'name': 'Gold', 'code': 'gold', 'sequence': 150,
            'threshold_fcfa': 1500000.0,
        })
        self.assertTrue(gold.id)
        partner = self.env['res.partner'].create({'name': 'Client Gold-1'})
        self._confirmed_so(partner, self.product_2m)
        partner.invalidate_recordset(['optical_customer_tier_id'])
        self.assertEqual(partner.optical_customer_tier_id, gold)

    def test_ac1_ondelete_restrict_referenced_tier(self):
        """AC-1.4 — un tier référencé par un plan ne peut pas être supprimé."""
        tier = self.Tier.create({
            'name': 'Temp', 'code': 'temp', 'sequence': 60,
            'threshold_fcfa': 300000.0,
        })
        self.env['optical.followup.plan'].create({
            'name': 'Plan réservé Temp', 'tier_id': tier.id,
        })
        with self.assertRaises(psycopg2.IntegrityError), \
                mute_logger('odoo.sql_db'):
            with self.env.cr.savepoint():
                tier.unlink()

    # ==================================================================
    # AC-2 — Calcul N tiers
    # ==================================================================

    def test_ac2_three_tier_calculation(self):
        """AC-2.2 — 3 tiers, seuils croissants : le plus haut atteint gagne."""
        gold = self.Tier.create({
            'name': 'Gold', 'code': 'gold', 'sequence': 150,
            'threshold_fcfa': 1500000.0,
        })
        # CA 100k → standard
        p1 = self.env['res.partner'].create({'name': 'N-tier 100k'})
        self._confirmed_so(p1, self.product_100k)
        p1.invalidate_recordset(['optical_customer_tier_id'])
        self.assertEqual(p1.optical_customer_tier_id, self.tier_standard)
        # CA 600k → vip (>= 500k, < 1.5M)
        p2 = self.env['res.partner'].create({'name': 'N-tier 600k'})
        self._confirmed_so(p2, self.product_600k)
        p2.invalidate_recordset(['optical_customer_tier_id'])
        self.assertEqual(p2.optical_customer_tier_id, self.tier_vip)
        # CA 2M → gold
        p3 = self.env['res.partner'].create({'name': 'N-tier 2M'})
        self._confirmed_so(p3, self.product_2m)
        p3.invalidate_recordset(['optical_customer_tier_id'])
        self.assertEqual(p3.optical_customer_tier_id, gold)

    def test_ac2_threshold_write_recomputes_partners(self):
        """AC-2.4 — write du seuil d'un tier recalcule les partners impactés."""
        partner = self.env['res.partner'].create({'name': 'Recompute test'})
        self._confirmed_so(partner, self.product_600k)
        partner.invalidate_recordset(['optical_customer_tier_id'])
        self.assertEqual(partner.optical_customer_tier_id, self.tier_vip)
        # Monter le seuil VIP au-dessus de 600k → recompute → standard
        self.tier_vip.threshold_fcfa = 700000.0
        partner.invalidate_recordset(['optical_customer_tier_id'])
        self.assertEqual(partner.optical_customer_tier_id, self.tier_standard)

    # ==================================================================
    # AC-3 — Override M2O
    # ==================================================================

    def test_ac3_override_forces_specific_tier(self):
        """AC-3.1 — override force un tier précis (pas seulement VIP)."""
        gold = self.Tier.create({
            'name': 'Gold', 'code': 'gold', 'sequence': 150,
            'threshold_fcfa': 1500000.0,
        })
        partner = self.env['res.partner'].create({'name': 'Override Gold'})
        partner.with_user(self.user_manager).write({
            'optical_customer_tier_override_id': gold.id,
        })
        partner.invalidate_recordset(['optical_customer_tier_id'])
        self.assertEqual(partner.optical_customer_tier_id, gold)

    def test_ac3_non_manager_cannot_override(self):
        """AC-3.2 — un non-manager ne peut pas écrire l'override."""
        partner = self.env['res.partner'].create({'name': 'Guard test'})
        with self.assertRaises(AccessError):
            partner.with_user(self.user_commercial).write({
                'optical_customer_tier_override_id': self.tier_vip.id,
            })

    def test_ac3_non_manager_cannot_override_on_create(self):
        """AC-3.2 (revue M1) — le garde-fou couvre aussi ``create``.

        Un non-manager ne doit pas pouvoir poser l'override à la création
        (porte dérobée ORM / import contournant la vue).
        """
        with self.assertRaises(AccessError):
            self.env['res.partner'].with_user(self.user_commercial).create({
                'name': 'Guard create',
                'optical_customer_tier_override_id': self.tier_vip.id,
            })

    def test_ac3_manager_can_override_on_create(self):
        """AC-3 (revue M1) — un manager conserve le droit de poser l'override
        à la création (non-régression du garde-fou)."""
        partner = self.env['res.partner'].with_user(self.user_manager).create({
            'name': 'Manager create override',
            'optical_customer_tier_override_id': self.tier_vip.id,
        })
        partner.invalidate_recordset(['optical_customer_tier_id'])
        self.assertEqual(partner.optical_customer_tier_id, self.tier_vip)

    # ==================================================================
    # AC-4 — Injection cumulative
    # ==================================================================

    def test_ac4_cumulative_injection_gold_gets_vip_steps(self):
        """AC-4.2 — un client Gold reçoit aussi les étapes réservées VIP."""
        gold = self.Tier.create({
            'name': 'Gold', 'code': 'gold', 'sequence': 150,
            'threshold_fcfa': 1500000.0,
        })
        # Plan réservé Gold avec 1 étape.
        gold_plan = self.env['optical.followup.plan'].create({
            'name': 'Étapes Gold', 'sequence': 120,
            'optical_type_trigger': 'any', 'tier_id': gold.id,
            'step_ids': [Command.create({
                'name': 'Conciergerie Gold', 'offset_days': 30,
                'sequence': 10,
                'activity_type_id': self.env.ref(
                    'mail.mail_activity_data_call',
                ).id,
            })],
        })
        partner = self.env['res.partner'].create({
            'name': 'Client Gold cumul',
            'optical_followup_consent': True,
            'birthdate': date(1985, 8, 15),
            'optical_customer_tier_override_id': gold.id,
        })
        so = self._deliver(partner, self.product_100k)
        schedule = so.followup_schedule_id
        reserved_lines = schedule.line_ids.filtered(
            lambda l: l.step_id.plan_id.tier_id
        )
        plans_seen = reserved_lines.mapped('step_id.plan_id')
        # Cumulatif : étapes du plan Gold ET du plan VIP (seq 100 <= 150)
        self.assertIn(gold_plan, plans_seen)
        self.assertIn(self.plan_vip_extra, plans_seen)
        # 1 (Gold) + 2 (VIP) = 3 lignes réservées
        self.assertEqual(len(reserved_lines), 3)

    def test_ac4_vip_partner_does_not_get_gold_steps(self):
        """AC-4.2 — la cumulativité est ascendante : un VIP ne reçoit PAS Gold."""
        gold = self.Tier.create({
            'name': 'Gold', 'code': 'gold', 'sequence': 150,
            'threshold_fcfa': 1500000.0,
        })
        self.env['optical.followup.plan'].create({
            'name': 'Étapes Gold', 'sequence': 120, 'tier_id': gold.id,
            'step_ids': [Command.create({
                'name': 'Conciergerie Gold', 'offset_days': 30,
                'activity_type_id': self.env.ref(
                    'mail.mail_activity_data_call',
                ).id,
            })],
        })
        partner = self.env['res.partner'].create({
            'name': 'Client VIP pas Gold',
            'optical_followup_consent': True,
            'birthdate': date(1985, 8, 15),
            'optical_customer_tier_override_id': self.tier_vip.id,
        })
        so = self._deliver(partner, self.product_100k)
        schedule = so.followup_schedule_id
        reserved_plans = schedule.line_ids.mapped('step_id.plan_id').filtered(
            'tier_id'
        )
        self.assertIn(self.plan_vip_extra, reserved_plans)
        self.assertNotIn(gold, reserved_plans.mapped('tier_id'))

    # ==================================================================
    # AC-5 — Robustesse seuil mal formé
    # ==================================================================

    def test_ac5_negative_threshold_tier_ignored(self):
        """AC-5.2 — un tier non-défaut à seuil <= 0 est ignoré au calcul."""
        bad = self.Tier.create({
            'name': 'Palier cassé', 'code': 'bad', 'sequence': 40,
            'threshold_fcfa': 0.0, 'is_default': False,
        })
        partner = self.env['res.partner'].create({'name': 'Seuil zéro'})
        self._confirmed_so(partner, self.product_100k)
        partner.invalidate_recordset(['optical_customer_tier_id'])
        # Malgré le tier cassé (seuil 0), le partner reste standard : le tier
        # à seuil <= 0 n'est jamais attribué automatiquement.
        self.assertEqual(partner.optical_customer_tier_id, self.tier_standard)
        self.assertNotEqual(partner.optical_customer_tier_id, bad)

    # ==================================================================
    # AC-6 — Migration V1 → 18-1
    # ==================================================================

    def _column_exists(self, table, column):
        self.env.cr.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            """,
            (table, column),
        )
        return bool(self.env.cr.fetchone())

    def test_ac6_migration_maps_v1_data(self):
        """AC-6 — mapping seuil / override / tier / plan depuis l'état V1."""
        cr = self.env.cr
        # 1. Recréer les colonnes V1 orphelines.
        cr.execute(
            "ALTER TABLE res_partner "
            "ADD COLUMN IF NOT EXISTS optical_customer_tier varchar"
        )
        cr.execute(
            "ALTER TABLE res_partner "
            "ADD COLUMN IF NOT EXISTS optical_customer_tier_override boolean"
        )
        cr.execute(
            "ALTER TABLE optical_followup_plan_step "
            "ADD COLUMN IF NOT EXISTS vip_only boolean"
        )
        # 2. Partner V1 « vip » + override booléen.
        partner = self.env['res.partner'].create({'name': 'Partner V1 vip'})
        cr.execute(
            "UPDATE res_partner SET optical_customer_tier = 'vip', "
            "optical_customer_tier_override = TRUE WHERE id = %s",
            (partner.id,),
        )
        # 3. Simuler l'absence de tier_id sur plan_vip_extra (état V1).
        self.plan_vip_extra.tier_id = False
        # 4. Seuil système V1.
        self.env['ir.config_parameter'].sudo().set_param(
            'optical_crm_followup.vip_threshold_fcfa', '700000',
        )

        # 5. Rejouer pre + post migration.
        pre = _load_migration('pre-migrate.py')
        post = _load_migration('post-migrate.py')
        pre.migrate(cr, '18.0.1.6.0')
        post.migrate(cr, '18.0.1.6.0')
        self.env.invalidate_all()

        # 6. Assertions.
        self.assertEqual(self.tier_vip.threshold_fcfa, 700000.0)
        self.assertEqual(self.plan_vip_extra.tier_id, self.tier_vip)
        self.assertEqual(
            partner.optical_customer_tier_override_id, self.tier_vip,
        )
        self.assertEqual(partner.optical_customer_tier_id, self.tier_vip)
        # Colonnes V1 supprimées.
        self.assertFalse(self._column_exists('res_partner', 'optical_customer_tier'))
        self.assertFalse(self._column_exists(
            'res_partner', 'optical_customer_tier_override',
        ))
        self.assertFalse(self._column_exists(
            'optical_followup_plan_step', 'vip_only',
        ))
        # Paramètres système nettoyés.
        self.assertFalse(self.env['ir.config_parameter'].sudo().get_param(
            'optical_crm_followup.vip_threshold_fcfa',
        ))

    def test_ac6_migration_idempotent(self):
        """AC-6.4 — rejouer la migration ne casse rien et ne duplique rien."""
        post = _load_migration('post-migrate.py')
        # Colonnes V1 déjà absentes (état post-upgrade normal) → tout est gardé.
        n_tiers_before = self.Tier.search_count([])
        post.migrate(self.env.cr, '18.0.1.6.0')
        self.env.invalidate_all()
        post.migrate(self.env.cr, '18.0.1.6.0')
        self.env.invalidate_all()
        self.assertEqual(self.Tier.search_count([]), n_tiers_before)
        self.assertEqual(self.plan_vip_extra.tier_id, self.tier_vip)
