# -*- coding: utf-8 -*-
"""Tests CC 6.6 — Montants manuels PEC et simplification workflow."""
from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestPecManualAmounts(OpticalTestCommon):
    """Tests montants manuels PEC, distribution proportionnelle et workflow simplifié."""

    def _create_order(self, policy=None, lines=None):
        """Helper : crée un devis avec lignes standard."""
        policy = policy or self.policy
        lines = lines or [
            Command.create({
                'product_id': self.product_monture.id,
                'product_uom_qty': 1,
                'price_unit': 50000.0,
            }),
            Command.create({
                'product_id': self.product_verre.id,
                'product_uom_qty': 1,
                'price_unit': 30000.0,
            }),
        ]
        return self.env['sale.order'].create({
            'partner_id': self.patient.id,
            'policy_id': policy.id,
            'order_line': lines,
        })

    def _approve_pec_for_order(self, order):
        """Helper : crée, soumet et approuve une PEC."""
        order.action_create_pec()
        order.action_confirm()
        pec = order.pec_id
        pec.action_submit()
        pec.with_user(self.user_responsable).action_approve()
        return pec

    # --- AC#1 : Saisie montant assurance approuvé ---

    def test_01_set_approved_amount(self):
        """AC#1 : on peut saisir amount_insurance_approved, amount_patient_approved se calcule."""
        order = self._create_order()
        pec = self._approve_pec_for_order(order)

        pec.write({'amount_insurance_approved': 60000.0})
        self.assertEqual(pec.amount_insurance_approved, 60000.0)
        self.assertAlmostEqual(
            pec.amount_patient_approved,
            order.amount_total - 60000.0,
            places=2,
        )

    def test_02_approved_amount_negative_rejected(self):
        """AC#1 : montant négatif → ValidationError."""
        order = self._create_order()
        pec = self._approve_pec_for_order(order)

        with self.assertRaises(ValidationError):
            pec.write({'amount_insurance_approved': -1000.0})

    def test_03_approved_amount_exceeds_total_rejected(self):
        """AC#1 : montant > total commande → ValidationError."""
        order = self._create_order()
        pec = self._approve_pec_for_order(order)
        total = order.amount_total

        with self.assertRaises(ValidationError):
            pec.write({'amount_insurance_approved': total + 1.0})

    # --- AC#2 : Distribution proportionnelle ---

    def test_04_proportional_distribution(self):
        """AC#2 : distribution proportionnelle sur les lignes du devis."""
        order = self._create_order()
        pec = self._approve_pec_for_order(order)

        pec.write({'amount_insurance_approved': 40000.0})
        pec.action_distribute_insurance()

        product_lines = order.order_line.filtered(lambda l: not l.display_type)
        total_distributed = sum(l.amount_insurance_line for l in product_lines)
        self.assertAlmostEqual(total_distributed, 40000.0, places=2)

        # Vérifier la proportionnalité (monture 50k/80k = 62.5%, verre 30k/80k = 37.5%)
        line_monture = product_lines.filtered(lambda l: l.product_id == self.product_monture)
        line_verre = product_lines.filtered(lambda l: l.product_id == self.product_verre)
        # 40000 * 50000/80000 = 25000
        self.assertAlmostEqual(line_monture.amount_insurance_line, 25000.0, places=2)
        # 40000 * 30000/80000 = 15000
        self.assertAlmostEqual(line_verre.amount_insurance_line, 15000.0, places=2)

    def test_05_distribution_rounding_correction(self):
        """AC#2 : la correction d'arrondi assure total == montant approuvé."""
        order = self._create_order()
        pec = self._approve_pec_for_order(order)

        # Montant qui ne se divise pas proprement
        pec.write({'amount_insurance_approved': 33333.0})
        pec.action_distribute_insurance()

        product_lines = order.order_line.filtered(lambda l: not l.display_type)
        total_distributed = sum(l.amount_insurance_line for l in product_lines)
        self.assertAlmostEqual(total_distributed, 33333.0, places=2)

    # --- AC#3 : Ajustement manuel par ligne ---

    def test_06_manual_line_adjustment(self):
        """AC#3 : on peut ajuster manuellement une ligne et la marquer manuelle."""
        order = self._create_order()
        pec = self._approve_pec_for_order(order)

        pec.write({'amount_insurance_approved': 50000.0})
        pec.action_distribute_insurance()

        # Ajuster manuellement la monture à 40000
        line_monture = order.order_line.filtered(
            lambda l: l.product_id == self.product_monture
        )
        line_monture.write({
            'amount_insurance_line': 40000.0,
            'is_insurance_manual': True,
        })

        # Re-distribuer : le verre doit recevoir le reliquat (50000 - 40000 = 10000)
        pec.action_distribute_insurance()

        line_verre = order.order_line.filtered(
            lambda l: l.product_id == self.product_verre
        )
        self.assertAlmostEqual(line_monture.amount_insurance_line, 40000.0, places=2)
        self.assertAlmostEqual(line_verre.amount_insurance_line, 10000.0, places=2)
        # Monture reste manuelle, verre non
        self.assertTrue(line_monture.is_insurance_manual)
        self.assertFalse(line_verre.is_insurance_manual)

    def test_07_manual_exceeds_approved_rejected(self):
        """AC#3 : somme lignes manuelles > montant approuvé → UserError."""
        order = self._create_order()
        pec = self._approve_pec_for_order(order)

        pec.write({'amount_insurance_approved': 30000.0})

        # Marquer une ligne avec montant > approuvé total
        line_monture = order.order_line.filtered(
            lambda l: l.product_id == self.product_monture
        )
        line_monture.write({
            'amount_insurance_line': 35000.0,
            'is_insurance_manual': True,
        })

        with self.assertRaises(UserError):
            pec.action_distribute_insurance()

    # --- AC#4 : Validation intégrité à la facturation ---

    def test_08_invoicing_integrity_check(self):
        """AC#4 : facturation échoue si sum(lines) ≠ amount_insurance_approved."""
        order = self._create_order()
        pec = self._approve_pec_for_order(order)

        pec.write({'amount_insurance_approved': 50000.0})
        # NE PAS distribuer — les lignes ont encore les montants estimation cascade
        # La somme ne correspondra pas au montant approuvé
        with self.assertRaises(ValidationError):
            pec.with_user(self.user_responsable).action_create_invoices()

    # --- AC#6 : Facturation avec montants manuels ---

    def test_09_invoicing_with_manual_amounts(self):
        """AC#6 : facturation split utilise les montants manuels approuvés."""
        order = self._create_order()
        pec = self._approve_pec_for_order(order)

        pec.write({'amount_insurance_approved': 40000.0})
        pec.action_distribute_insurance()

        pec.with_user(self.user_responsable).action_create_invoices()
        self.assertEqual(pec.state, 'invoiced')

        # Vérifier intégrité comptable NFR9
        ins_total = pec.invoice_insurance_id.amount_total
        tm_total = pec.invoice_tm_id.amount_total
        self.assertAlmostEqual(
            ins_total + tm_total, order.amount_total, places=2,
            msg="NFR9 : assurance + TM == total commande.",
        )

    def test_10_invoicing_full_coverage_manual(self):
        """AC#6 : montant approuvé == total → pas de TM."""
        order = self._create_order()
        pec = self._approve_pec_for_order(order)

        total = order.amount_total
        pec.write({'amount_insurance_approved': total})
        pec.action_distribute_insurance()

        pec.with_user(self.user_responsable).action_create_invoices()
        self.assertTrue(pec.invoice_insurance_id)
        self.assertFalse(pec.invoice_tm_id, "Pas de TM quand couverture 100%")
        self.assertAlmostEqual(
            pec.invoice_insurance_id.amount_total, total, places=2,
        )

    # --- AC#9-10 : Reset approved → submitted ---

    def test_11_reset_to_submitted_ok(self):
        """AC#9 : PEC approuvée sans factures → peut être remise en soumis."""
        order = self._create_order()
        pec = self._approve_pec_for_order(order)

        pec.write({'amount_insurance_approved': 50000.0})
        pec.action_distribute_insurance()

        pec.with_user(self.user_responsable).action_reset_to_submitted()
        self.assertEqual(pec.state, 'submitted')
        self.assertEqual(pec.amount_insurance_approved, 0)
        self.assertFalse(pec.date_approved)

        # Vérifier que les montants par ligne sont revenus à l'estimation
        product_lines = order.order_line.filtered(lambda l: not l.display_type)
        for line in product_lines:
            self.assertFalse(line.is_insurance_manual)

    def test_12_reset_to_submitted_blocked_if_invoiced(self):
        """AC#10 : PEC facturée → erreur si on tente de remettre en soumis."""
        order = self._create_order()
        pec = self._approve_pec_for_order(order)

        pec.with_user(self.user_responsable).action_create_invoices()
        self.assertEqual(pec.state, 'invoiced')

        # Remettre en approved pour tester le guard
        # Impossible car invoiced ne peut pas aller en submitted directement
        # et action_reset_to_submitted vérifie state == approved
        # Le test vérifie que le guard state != approved bloque
        with self.assertRaises(UserError):
            pec.with_user(self.user_responsable).action_reset_to_submitted()

    def test_13_reset_to_submitted_blocked_if_invoices_exist(self):
        """AC#10 : PEC approuvée mais avec factures → erreur."""
        order = self._create_order()
        pec = self._approve_pec_for_order(order)

        # Générer factures
        pec.with_user(self.user_responsable).action_create_invoices()
        self.assertEqual(pec.state, 'invoiced')

        # Forcer l'état approved pour tester le guard des factures
        pec.write({'state': 'approved'})
        with self.assertRaises(UserError):
            pec.with_user(self.user_responsable).action_reset_to_submitted()

    # --- AC#12 : payment_status ---

    def test_14_payment_status_none(self):
        """AC#12 : PEC sans factures → payment_status = none."""
        order = self._create_order()
        pec = self._approve_pec_for_order(order)
        self.assertEqual(pec.payment_status, 'none')

    def test_15_payment_status_not_paid(self):
        """AC#12 : factures créées non payées → payment_status = not_paid."""
        order = self._create_order()
        pec = self._approve_pec_for_order(order)
        pec.with_user(self.user_responsable).action_create_invoices()

        self.assertEqual(pec.payment_status, 'not_paid')

    # --- AC#13 : Mode estimation (approved_amount = 0 → cascade) ---

    def test_16_estimation_mode_cascade(self):
        """AC#13 : si amount_insurance_approved == 0, facturation utilise la cascade."""
        order = self._create_order()
        pec = self._approve_pec_for_order(order)

        # Ne pas setter amount_insurance_approved (reste à 0)
        self.assertEqual(pec.amount_insurance_approved, 0)

        pec.with_user(self.user_responsable).action_create_invoices()
        self.assertEqual(pec.state, 'invoiced')
        self.assertTrue(pec.invoice_insurance_id)

        # Le montant assurance doit correspondre à l'estimation cascade
        ins_total = pec.invoice_insurance_id.amount_total
        self.assertGreater(ins_total, 0, "L'estimation cascade doit produire un montant > 0")

    # --- AC#7 : Cascade 3 niveaux ---

    def test_17_cascade_with_optical_type(self):
        """AC#7 : cascade Plan rule > Plan default — produits avec optical_type."""
        # Créer produits avec optical_type pour activer les coverage rules
        monture_typed = self.env['product.product'].create({
            'name': 'Monture Typée',
            'type': 'consu',
            'list_price': 50000.0,
            'taxes_id': [],
            'optical_type': 'frame',
        })
        verre_typed = self.env['product.product'].create({
            'name': 'Verre Typé',
            'type': 'consu',
            'list_price': 30000.0,
            'taxes_id': [],
            'optical_type': 'lens',
        })
        order = self._create_order(lines=[
            Command.create({
                'product_id': monture_typed.id,
                'product_uom_qty': 1,
                'price_unit': 50000.0,
            }),
            Command.create({
                'product_id': verre_typed.id,
                'product_uom_qty': 1,
                'price_unit': 30000.0,
            }),
        ])

        line_monture = order.order_line.filtered(lambda l: l.product_id == monture_typed)
        line_verre = order.order_line.filtered(lambda l: l.product_id == verre_typed)

        # Monture : frame rule = 70%, reference_price=50000, min(50000,50000)*70% = 35000
        self.assertAlmostEqual(line_monture.amount_insurance_line, 35000.0, places=2)
        # Verre : lens rule = 90%, 30000 * 90% = 27000
        self.assertAlmostEqual(line_verre.amount_insurance_line, 27000.0, places=2)

    def test_18_cascade_fallback_to_plan_default(self):
        """AC#7 : produit sans règle catégorie → taux par défaut du plan."""
        # Produit sans optical_type → pas de coverage_rule → fallback plan default (80%)
        product_accessoire = self.env['product.product'].create({
            'name': 'Étui Test',
            'type': 'consu',
            'list_price': 10000.0,
            'taxes_id': [],
        })
        order = self._create_order(lines=[
            Command.create({
                'product_id': product_accessoire.id,
                'product_uom_qty': 1,
                'price_unit': 10000.0,
            }),
        ])

        line = order.order_line.filtered(lambda l: not l.display_type)
        # Plan default = 80%, 10000 * 0.8 = 8000
        self.assertAlmostEqual(line.amount_insurance_line, 8000.0, places=2)

    # --- AC#5 : Redistribution automatique via onchange ---

    def test_19_onchange_resets_manual_and_redistributes(self):
        """AC#5 : onchange amount_insurance_approved réinitialise les flags manuels et redistribue."""
        order = self._create_order()
        pec = self._approve_pec_for_order(order)

        # Distribuer une première fois
        pec.write({'amount_insurance_approved': 50000.0})
        pec.action_distribute_insurance()

        # Marquer une ligne manuellement
        line_monture = order.order_line.filtered(
            lambda l: l.product_id == self.product_monture
        )
        line_monture.write({'is_insurance_manual': True})
        self.assertTrue(line_monture.is_insurance_manual)

        # Simuler onchange avec nouveau montant
        pec._onchange_amount_insurance_approved()

        # Les flags manuels doivent être réinitialisés
        self.assertFalse(line_monture.is_insurance_manual)
        # La distribution doit avoir eu lieu
        product_lines = order.order_line.filtered(lambda l: not l.display_type)
        total_distributed = sum(l.amount_insurance_line for l in product_lines)
        self.assertAlmostEqual(total_distributed, 50000.0, places=2)

    # --- Tests supplémentaires ---

    def test_20_distribution_only_on_approved(self):
        """Distribution impossible sur PEC non approuvée."""
        order = self._create_order()
        order.action_create_pec()
        order.action_confirm()
        pec = order.pec_id

        with self.assertRaises(UserError):
            pec.action_distribute_insurance()

    def test_21_estimation_updates_on_policy_change(self):
        """Les estimations se recalculent quand la police change."""
        order = self._create_order()
        product_lines = order.order_line.filtered(lambda l: not l.display_type)

        # Estimations initiales avec policy (80% default, rules frame 70%, lens 90%)
        initial_amounts = {l.id: l.amount_insurance_line for l in product_lines}
        self.assertTrue(all(v > 0 for v in initial_amounts.values()))

        # Changer vers policy_full (100%)
        order.write({'policy_id': self.policy_full.id})

        # Les montants doivent être recalculés
        for line in product_lines:
            self.assertAlmostEqual(
                line.amount_insurance_line, line.price_total, places=2,
                msg="Avec couverture 100%, part assurance = prix total.",
            )

    def test_22_estimation_reset_on_policy_removal(self):
        """Les estimations passent à 0 quand la police est retirée."""
        order = self._create_order()
        product_lines = order.order_line.filtered(lambda l: not l.display_type)
        self.assertTrue(all(l.amount_insurance_line > 0 for l in product_lines))

        order.write({'policy_id': False})
        for line in product_lines:
            self.assertEqual(line.amount_insurance_line, 0.0)
