# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestSaleOrderInsurance(OpticalTestCommon):
    """Tests pour l'extension sale.order avec calcul assurance/TM (Story 2.2)."""

    def test_compute_insurance_amounts(self):
        """Test calcul assurance : montants calcules selon le taux de couverture."""
        self.sale_order.write({'policy_id': self.policy.id})
        # Taux 80%, total = 80000 (50000 + 30000)
        self.assertEqual(self.sale_order.amount_insurance, 64000.0)
        self.assertEqual(self.sale_order.amount_patient, 16000.0)

    def test_insurance_integrity(self):
        """Test integrite comptable : amount_insurance + amount_patient == amount_total (NFR9)."""
        self.sale_order.write({'policy_id': self.policy.id})
        self.assertAlmostEqual(
            self.sale_order.amount_insurance + self.sale_order.amount_patient,
            self.sale_order.amount_total,
            places=2,
            msg="La somme part assurance + TM doit etre egale au total TTC",
        )

    def test_no_policy_standard_workflow(self):
        """Test sans police : workflow standard Odoo fonctionne sans erreur (NFR15, FR27)."""
        self.assertFalse(self.sale_order.policy_id)
        self.assertEqual(self.sale_order.amount_insurance, 0.0)
        self.assertEqual(self.sale_order.amount_patient, 0.0)
        # Confirmer la commande — workflow standard
        self.sale_order.action_confirm()
        self.assertEqual(self.sale_order.state, 'sale')
        # Creer la facture — workflow standard
        invoice = self.sale_order._create_invoices()
        self.assertTrue(invoice)
        self.assertEqual(invoice.move_type, 'out_invoice')

    def test_has_insurance(self):
        """Test has_insurance : True quand policy_id renseigne, False sinon (FR30)."""
        self.assertFalse(self.sale_order.has_insurance)
        self.sale_order.write({'policy_id': self.policy.id})
        self.assertTrue(self.sale_order.has_insurance)

    def test_line_insurance_amounts(self):
        """Test prorata par ligne : montants corrects sur chaque ligne."""
        self.sale_order.write({'policy_id': self.policy.id})
        line_monture = self.sale_order.order_line.filtered(
            lambda l: l.product_id == self.product_monture
        )
        line_verre = self.sale_order.order_line.filtered(
            lambda l: l.product_id == self.product_verre
        )
        # Monture 50000 * 80% = 40000 assurance, 10000 patient
        self.assertEqual(line_monture.amount_insurance_line, 40000.0)
        self.assertEqual(line_monture.amount_patient_line, 10000.0)
        # Verre 30000 * 80% = 24000 assurance, 6000 patient
        self.assertEqual(line_verre.amount_insurance_line, 24000.0)
        self.assertEqual(line_verre.amount_patient_line, 6000.0)

    def test_change_policy(self):
        """Test changement police : montants reviennent a 0 quand police retiree."""
        self.sale_order.write({'policy_id': self.policy.id})
        self.assertEqual(self.sale_order.amount_insurance, 64000.0)
        self.assertTrue(self.sale_order.has_insurance)
        # Retirer la police
        self.sale_order.write({'policy_id': False})
        self.assertEqual(self.sale_order.amount_insurance, 0.0)
        self.assertEqual(self.sale_order.amount_patient, 0.0)
        self.assertFalse(self.sale_order.has_insurance)

    def test_split_invoice_button_works(self):
        """Test bouton : action_create_split_invoices fonctionne sur commande valide (Story 2.3)."""
        self.sale_order.write({'policy_id': self.policy.id})
        pec = self._approve_pec()
        self.assertEqual(pec.state, 'approved')
        result = self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        self.assertEqual(result['type'], 'ir.actions.act_window')
        invoices = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
        ])
        self.assertEqual(len(invoices), 2)

    def test_confirm_insurance_order_without_pec_raises(self):
        """Confirmer un devis assurance sans PEC → UserError."""
        self.sale_order.write({'policy_id': self.policy.id})
        self.assertTrue(self.sale_order.has_insurance)
        self.assertFalse(self.sale_order.pec_id)
        with self.assertRaises(UserError):
            self.sale_order.action_confirm()

    def test_confirm_insurance_order_with_pec_ok(self):
        """Confirmer un devis assurance avec PEC → OK."""
        self.sale_order.write({'policy_id': self.policy.id})
        self.sale_order.action_create_pec()
        self.assertTrue(self.sale_order.pec_id)
        self.sale_order.action_confirm()
        self.assertEqual(self.sale_order.state, 'sale')

    # --- Tests review : vendeur, cas limites, arrondi ---

    def test_vendeur_can_set_policy(self):
        """Test M1: Le vendeur optique peut selectionner une police et voir les montants."""
        # Assigner le vendeur comme commercial du devis (record rules)
        self.sale_order.write({'user_id': self.user_vendeur.id})
        order = self.sale_order.with_user(self.user_vendeur)
        order.write({'policy_id': self.policy.id})
        self.assertEqual(order.amount_insurance, 64000.0)
        self.assertEqual(order.amount_patient, 16000.0)
        self.assertTrue(order.has_insurance)

    def test_coverage_rate_zero(self):
        """Test M2: Taux 0% — aucune couverture, tout a la charge du patient."""
        self.policy.write({'coverage_rate': 0.0, 'plan_id': False})
        self.sale_order.write({'policy_id': self.policy.id})
        self.assertEqual(self.sale_order.amount_insurance, 0.0)
        self.assertEqual(self.sale_order.amount_patient, 80000.0)

    def test_coverage_rate_full(self):
        """Test M2: Taux 100% — couverture totale, patient paie 0."""
        self.policy.write({'coverage_rate': 100.0, 'plan_id': False})
        self.sale_order.write({'policy_id': self.policy.id})
        self.assertEqual(self.sale_order.amount_insurance, 80000.0)
        self.assertEqual(self.sale_order.amount_patient, 0.0)

    def test_coverage_rate_fractional(self):
        """Test M2: Taux non rond (67.5%) — verifie l'arrondi."""
        self.policy.write({'coverage_rate': 67.5, 'plan_id': False})
        self.sale_order.write({'policy_id': self.policy.id})
        # 80000 * 67.5% = 54000.0
        self.assertEqual(self.sale_order.amount_insurance, 54000.0)
        self.assertEqual(self.sale_order.amount_patient, 26000.0)
        self.assertAlmostEqual(
            self.sale_order.amount_insurance + self.sale_order.amount_patient,
            self.sale_order.amount_total,
            places=2,
        )

    def test_rounding_fractional_amounts(self):
        """Test M3: Arrondi avec montants non ronds — integrite malgre arrondis."""
        # Utiliser le devis partage avec un taux non rond pour forcer l'arrondi
        self.policy.write({'coverage_rate': 33.33, 'plan_id': False})
        self.sale_order.write({'policy_id': self.policy.id})
        # total = 80000, 80000 * 33.33% = 26664.0, patient = 53336.0
        self.assertAlmostEqual(
            self.sale_order.amount_insurance + self.sale_order.amount_patient,
            self.sale_order.amount_total,
            places=2,
            msg="Integrite comptable NFR9 preservee malgre arrondi",
        )
        self.assertGreater(self.sale_order.amount_insurance, 0)
        self.assertGreater(self.sale_order.amount_patient, 0)

    def test_policy_wrong_patient_raises(self):
        """Test H2: Validation serveur — police d'un autre patient refuse."""
        other_patient = self.env['res.partner'].create({
            'name': 'Autre Patient',
            'is_patient': True,
        })
        other_policy = self.env['optical.policy'].create({
            'patient_id': other_patient.id,
            'insurer_id': self.insurer.id,
            'coverage_rate': 80.0,
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',

        })
        with self.assertRaises(ValidationError):
            self.sale_order.write({'policy_id': other_policy.id})

    def test_policy_expired_raises(self):
        """Test H2: Validation serveur — police expiree refuse."""
        expired_policy = self.env['optical.policy'].create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'coverage_rate': 80.0,
            'date_start': '2025-01-01',
            'date_end': '2025-12-31',
            'state': 'expired',

        })
        with self.assertRaises(ValidationError):
            self.sale_order.write({'policy_id': expired_policy.id})

    # --- Tests Story 5.1 : Cascade de couverture ---

    def test_cascade_coverage_rule(self):
        """Cascade : produit avec optical_type → utilise le taux de la règle."""
        # Assigner optical_type sur les produits
        self.product_monture.product_tmpl_id.write({'optical_type': 'frame'})
        self.product_verre.product_tmpl_id.write({'optical_type': 'lens'})
        self.sale_order.write({'policy_id': self.policy.id})
        # La monture utilise la règle frame (70%) — mais avec reference_price 50000
        # price_unit = 50000, min(50000, 50000) = 50000, 50000 * 70% = 35000
        line_monture = self.sale_order.order_line.filtered(
            lambda l: l.product_id == self.product_monture
        )
        self.assertEqual(line_monture.amount_insurance_line, 35000.0)
        # Le verre utilise la règle lens (90%) — pas de reference_price
        # 30000 * 90% = 27000
        line_verre = self.sale_order.order_line.filtered(
            lambda l: l.product_id == self.product_verre
        )
        self.assertEqual(line_verre.amount_insurance_line, 27000.0)

    def test_cascade_fallback_plan_rate(self):
        """Cascade : produit sans optical_type → utilise le taux par défaut du plan."""
        # Produits sans optical_type → fallback au taux du plan (80%)
        self.product_monture.product_tmpl_id.write({'optical_type': False})
        self.product_verre.product_tmpl_id.write({'optical_type': False})
        self.sale_order.write({'policy_id': self.policy.id})
        # 80000 * 80% = 64000
        self.assertEqual(self.sale_order.amount_insurance, 64000.0)
        self.assertEqual(self.sale_order.amount_patient, 16000.0)

    def test_cascade_fallback_policy_rate(self):
        """Cascade : police SANS plan → utilise le taux de la police (rétrocompatible)."""
        policy_no_plan = self.env['optical.policy'].create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'coverage_rate': 60.0,
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',

        })
        self.sale_order.write({'policy_id': policy_no_plan.id})
        # 80000 * 60% = 48000
        self.assertEqual(self.sale_order.amount_insurance, 48000.0)
        self.assertEqual(self.sale_order.amount_patient, 32000.0)

    def test_reference_price_capping(self):
        """Cascade : reference_price plafonne la base de calcul."""
        self.product_monture.product_tmpl_id.write({'optical_type': 'frame'})
        # reference_price = 50000, monture à 80000 → covered_base = 50000
        # 50000 * 70% = 35000
        order = self.env['sale.order'].create({
            'partner_id': self.patient.id,
            'policy_id': self.policy.id,


            'order_line': [
                Command.create({
                    'product_id': self.product_monture.id,
                    'product_uom_qty': 1,
                    'price_unit': 80000.0,
                }),
            ],
        })
        line = order.order_line[0]
        self.assertEqual(line.amount_insurance_line, 35000.0)
        self.assertEqual(line.amount_patient_line, 45000.0)


@tagged('post_install', '-at_install')
class TestSaleOrderPrescription(OpticalTestCommon):
    """Tests pour la liaison ordonnance-commande et onglet mesures (Story 3.3)."""

    def test_select_confirmed_prescription(self):
        """AC #1, #3: Sélection d'une ordonnance confirmée — champs related remplis."""
        self.sale_order.write({'prescription_id': self.prescription_confirmed.id})
        self.assertEqual(self.sale_order.prescription_id, self.prescription_confirmed)
        self.assertEqual(self.sale_order.prescription_od_sphere, 2.50)
        self.assertEqual(self.sale_order.prescription_og_sphere, 3.00)

    def test_expired_prescription_rejected(self):
        """AC #2: Ordonnance expirée — ValidationError au save."""
        expired_rx = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'od_sphere': 1.00,
            'date': '2020-01-01',

        })
        expired_rx.action_confirm()
        expired_rx.write({'state': 'expired'})
        with self.assertRaises(ValidationError):
            self.sale_order.write({'prescription_id': expired_rx.id})

    def test_measures_displayed_correctly(self):
        """AC #4: Les champs related reflètent les mesures de l'ordonnance."""
        self.sale_order.write({'prescription_id': self.prescription_confirmed.id})
        self.assertEqual(self.sale_order.prescription_od_sphere, 2.50)
        self.assertEqual(self.sale_order.prescription_od_cylinder, -1.25)
        self.assertEqual(self.sale_order.prescription_od_axis, 90)
        self.assertEqual(self.sale_order.prescription_od_addition, 1.50)
        self.assertEqual(self.sale_order.prescription_od_pd, 32.0)
        self.assertEqual(self.sale_order.prescription_og_sphere, 3.00)
        self.assertEqual(self.sale_order.prescription_og_cylinder, -0.75)
        self.assertEqual(self.sale_order.prescription_og_axis, 85)
        self.assertEqual(self.sale_order.prescription_og_addition, 1.50)
        self.assertEqual(self.sale_order.prescription_og_pd, 31.5)
        self.assertEqual(self.sale_order.prescription_pd_total, 63.5)
        self.assertEqual(self.sale_order.prescription_notes, 'Port permanent')

    def test_no_prescription_empty_measures(self):
        """AC #5: Sans ordonnance — champs related vides/False."""
        self.assertFalse(self.sale_order.prescription_id)
        self.assertEqual(self.sale_order.prescription_od_sphere, 0.0)
        self.assertEqual(self.sale_order.prescription_og_sphere, 0.0)
        self.assertFalse(self.sale_order.prescription_notes)

    def test_change_prescription_updates_measures(self):
        """AC #6: Changement d'ordonnance — mesures mises à jour."""
        self.sale_order.write({'prescription_id': self.prescription_confirmed.id})
        self.assertEqual(self.sale_order.prescription_od_sphere, 2.50)

        # Créer une deuxième ordonnance confirmée avec des mesures différentes
        rx_b = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'od_sphere': -3.00,
            'og_sphere': -2.50,
            'od_pd': 30.0,
            'og_pd': 30.5,
            'pd_total': 60.5,

        })
        rx_b.action_confirm()
        self.sale_order.write({'prescription_id': rx_b.id})
        self.assertEqual(self.sale_order.prescription_od_sphere, -3.00)
        self.assertEqual(self.sale_order.prescription_og_sphere, -2.50)
        self.assertEqual(self.sale_order.prescription_pd_total, 60.5)

    def test_prescription_patient_mismatch_rejected(self):
        """AC #7: Ordonnance d'un autre patient — ValidationError."""
        other_patient = self.env['res.partner'].create({
            'name': 'Autre Patient Rx',
            'is_patient': True,
        })
        other_rx = self.env['optical.prescription'].create({
            'patient_id': other_patient.id,
            'prescriber_id': self.prescriber.id,
            'od_sphere': 1.00,

        })
        other_rx.action_confirm()
        with self.assertRaises(ValidationError):
            self.sale_order.write({'prescription_id': other_rx.id})

    def test_confirmed_order_prescription_readonly(self):
        """AC #8: Commande confirmée — prescription_id en lecture seule, mesures visibles."""
        self.sale_order.write({'prescription_id': self.prescription_confirmed.id})
        self.sale_order.action_confirm()
        self.assertEqual(self.sale_order.state, 'sale')
        # Les mesures restent accessibles après confirmation
        self.assertEqual(self.sale_order.prescription_od_sphere, 2.50)
        self.assertEqual(self.sale_order.prescription_id, self.prescription_confirmed)
        # Vérifier que prescription_id est readonly sur commande confirmée via la vue
        arch = self.env['sale.order'].get_view(view_type='form')['arch']
        from lxml import etree
        tree = etree.fromstring(arch)
        rx_fields = tree.xpath("//field[@name='prescription_id']")
        self.assertTrue(rx_fields, "Le champ prescription_id doit être présent dans la vue form")
        readonly_expr = rx_fields[0].get('readonly', '')
        self.assertIn('draft', readonly_expr,
                      "prescription_id doit être readonly hors états draft/sent")

    def test_prescription_domain_filters_by_patient(self):
        """AC #7 (domain): Le domain filtre par partner_id du devis."""
        # Vérifier que le domain du champ prescription_id filtre correctement
        field = self.env['sale.order']._fields['prescription_id']
        self.assertIn("('patient_id', '=', partner_id)", field.domain)
