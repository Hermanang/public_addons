# -*- coding: utf-8 -*-
import time

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestAccountMoveSplitInvoice(OpticalTestCommon):
    """Tests pour la facturation split assurance/TM (Story 2.3)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Configurer la commande avec police, PEC approuvée et confirmer
        cls.sale_order.write({'policy_id': cls.policy.id})
        cls._approve_pec()

    def test_split_invoice_creation(self):
        """Test création split : 2 factures créées avec les bons types."""
        result = self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        invoices = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
            ('move_type', '=', 'out_invoice'),
        ])
        self.assertEqual(len(invoices), 2)
        self.assertTrue(invoices.filtered('is_insurance_invoice'))
        self.assertTrue(invoices.filtered('is_tm_invoice'))

    def test_split_invoice_partners(self):
        """Test partenaires corrects : assurance → assureur, TM → patient."""
        self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        invoices = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
        ])
        ins_invoice = invoices.filtered('is_insurance_invoice')
        tm_invoice = invoices.filtered('is_tm_invoice')
        self.assertEqual(ins_invoice.partner_id, self.policy.insurer_id)
        self.assertEqual(tm_invoice.partner_id, self.patient)

    def test_split_invoice_prorated_amounts(self):
        """Test montants proratisés HT : 80% assurance, 20% patient."""
        self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        invoices = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
        ])
        ins_invoice = invoices.filtered('is_insurance_invoice')
        tm_invoice = invoices.filtered('is_tm_invoice')
        # Total HT = 80000, assurance 80% = 64000, TM 20% = 16000
        # (produits de test sans taxe → HT = TTC)
        ins_total = sum(ins_invoice.invoice_line_ids.mapped('price_subtotal'))
        tm_total = sum(tm_invoice.invoice_line_ids.mapped('price_subtotal'))
        self.assertAlmostEqual(ins_total, 64000.0, places=2)
        self.assertAlmostEqual(tm_total, 16000.0, places=2)

    def test_split_invoice_accounting_integrity(self):
        """Test intégrité comptable NFR9 : assurance HT + TM HT == HT commande."""
        self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        invoices = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
        ])
        ins_invoice = invoices.filtered('is_insurance_invoice')
        tm_invoice = invoices.filtered('is_tm_invoice')
        ins_total = sum(ins_invoice.invoice_line_ids.mapped('price_subtotal'))
        tm_total = sum(tm_invoice.invoice_line_ids.mapped('price_subtotal'))
        self.assertAlmostEqual(
            ins_total + tm_total,
            self.sale_order.amount_untaxed,
            places=2,
            msg="Intégrité comptable : assurance HT + TM HT doit être égal au HT commande",
        )

    def test_split_invoice_real_products(self):
        """Test vrais produits : chaque ligne contient le product_id original."""
        self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        invoices = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
        ])
        order_products = self.sale_order.order_line.mapped('product_id')
        for invoice in invoices:
            invoice_products = invoice.invoice_line_ids.mapped('product_id')
            self.assertEqual(
                set(invoice_products.ids),
                set(order_products.ids),
                "Chaque facture doit contenir les vrais produits de la commande",
            )

    def test_split_invoice_same_taxes_both(self):
        """Test taxes identiques : assurance et TM ont les mêmes taxes que le produit."""
        self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        invoices = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
        ])
        ins_invoice = invoices.filtered('is_insurance_invoice')
        tm_invoice = invoices.filtered('is_tm_invoice')
        # Les taxes sur chaque ligne doivent être identiques entre assurance et TM
        for ins_line, tm_line in zip(
            ins_invoice.invoice_line_ids.sorted('product_id'),
            tm_invoice.invoice_line_ids.sorted('product_id'),
        ):
            self.assertEqual(
                ins_line.tax_ids, tm_line.tax_ids,
                "Les taxes doivent être identiques sur les deux factures",
            )

    def test_split_invoice_traceability(self):
        """Test traçabilité : insurance_sale_order_id et insurance_policy_id renseignés."""
        self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        invoices = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
        ])
        for invoice in invoices:
            self.assertEqual(invoice.insurance_sale_order_id, self.sale_order)
            self.assertEqual(invoice.insurance_policy_id, self.policy)

    def test_split_invoice_duplicate_blocked(self):
        """Test doublon bloqué : 2ème appel → UserError."""
        self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        with self.assertRaises(UserError):
            self.sale_order.with_user(self.user_responsable).action_create_split_invoices()

    def test_split_invoice_no_policy(self):
        """Test sans police : UserError."""
        order = self.env['sale.order'].create({
            'partner_id': self.patient.id,


            'order_line': [
                Command.create({
                    'product_id': self.product_monture.id,
                    'product_uom_qty': 1,
                    'price_unit': 50000.0,
                }),
            ],
        })
        order.action_confirm()
        with self.assertRaises(UserError):
            order.action_create_split_invoices()

    def test_split_invoice_draft_state(self):
        """Test état incorrect : commande en brouillon → UserError."""
        order = self.env['sale.order'].create({
            'partner_id': self.patient.id,
            'policy_id': self.policy.id,


            'order_line': [
                Command.create({
                    'product_id': self.product_monture.id,
                    'product_uom_qty': 1,
                    'price_unit': 50000.0,
                }),
            ],
        })
        with self.assertRaises(UserError):
            order.action_create_split_invoices()

    def test_unlink_posted_insurance_invoice_blocked(self):
        """Suppression facture assurance postée → UserError."""
        self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        ins_invoice = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
            ('is_insurance_invoice', '=', True),
        ])
        ins_invoice.action_post()
        with self.assertRaises(UserError):
            ins_invoice.unlink()

    def test_unlink_posted_tm_invoice_blocked(self):
        """Suppression facture TM postée → UserError."""
        self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        tm_invoice = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
            ('is_tm_invoice', '=', True),
        ])
        tm_invoice.action_post()
        with self.assertRaises(UserError):
            tm_invoice.unlink()

    def test_unlink_draft_insurance_deletes_couple(self):
        """Suppression facture assurance brouillon → couple entier supprimé."""
        self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        ins_invoice = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
            ('is_insurance_invoice', '=', True),
        ])
        tm_invoice = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
            ('is_tm_invoice', '=', True),
        ])
        self.assertEqual(ins_invoice.state, 'draft')
        self.assertEqual(tm_invoice.state, 'draft')

        ins_invoice.unlink()

        # Les deux factures doivent avoir été supprimées
        remaining = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
            ('move_type', '=', 'out_invoice'),
        ])
        self.assertFalse(remaining)

    def test_unlink_draft_tm_deletes_couple(self):
        """Suppression facture TM brouillon → couple entier supprimé."""
        self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        tm_invoice = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
            ('is_tm_invoice', '=', True),
        ])
        self.assertEqual(tm_invoice.state, 'draft')

        tm_invoice.unlink()

        remaining = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
            ('move_type', '=', 'out_invoice'),
        ])
        self.assertFalse(remaining)

    def test_unlink_draft_cleans_pec(self):
        """Suppression brouillon → PEC nettoyée (state approved, refs vides)."""
        pec = self.sale_order.pec_id
        pec.with_user(self.user_responsable).action_create_invoices()
        self.assertEqual(pec.state, 'invoiced')
        self.assertTrue(pec.invoice_insurance_id)

        ins_invoice = pec.invoice_insurance_id
        self.assertEqual(ins_invoice.state, 'draft')

        ins_invoice.unlink()

        self.assertEqual(pec.state, 'approved')
        self.assertFalse(pec.invoice_insurance_id)
        self.assertFalse(pec.invoice_tm_id)

    def test_unlink_draft_allows_regeneration(self):
        """Après suppression brouillon → re-génération possible et intégrité NFR9."""
        self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        ins_invoice = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
            ('is_insurance_invoice', '=', True),
        ])
        ins_invoice.unlink()

        # Re-générer
        self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        invoices = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
            ('move_type', '=', 'out_invoice'),
        ])
        self.assertEqual(len(invoices), 2)

        # Intégrité comptable NFR9
        ins_total = sum(invoices.filtered('is_insurance_invoice').invoice_line_ids.mapped('price_subtotal'))
        tm_total = sum(invoices.filtered('is_tm_invoice').invoice_line_ids.mapped('price_subtotal'))
        self.assertAlmostEqual(
            ins_total + tm_total,
            self.sale_order.amount_untaxed,
            places=2,
        )

    def test_unlink_draft_resets_invoice_status(self):
        """Après suppression brouillon → invoice_status revient à 'to invoice'."""
        self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        self.assertEqual(self.sale_order.invoice_status, 'invoiced')

        tm_invoice = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
            ('is_tm_invoice', '=', True),
        ])
        tm_invoice.unlink()

        # qty_invoiced doit être revenu à 0, donc invoice_status != 'invoiced'
        self.sale_order.invalidate_recordset()
        self.assertNotEqual(self.sale_order.invoice_status, 'invoiced')

    def test_unlink_mixed_state_blocked(self):
        """Suppression mixte (un brouillon + un posté) → UserError."""
        self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        ins_invoice = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
            ('is_insurance_invoice', '=', True),
        ])
        tm_invoice = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
            ('is_tm_invoice', '=', True),
        ])
        # Poster uniquement l'assurance
        ins_invoice.action_post()
        self.assertEqual(ins_invoice.state, 'posted')
        self.assertEqual(tm_invoice.state, 'draft')

        # Tenter de supprimer le TM (brouillon) → bloqué car jumelle postée
        with self.assertRaises(UserError):
            tm_invoice.unlink()

    def test_unlink_draft_both_at_once(self):
        """Suppression simultanée des deux factures du couple → suppression OK."""
        self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        invoices = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
            ('move_type', '=', 'out_invoice'),
        ])
        self.assertEqual(len(invoices), 2)

        # Supprimer les deux en un seul appel
        invoices.unlink()

        remaining = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
            ('move_type', '=', 'out_invoice'),
        ])
        self.assertFalse(remaining)

    def test_unlink_draft_cleans_pec_full_coverage(self):
        """Suppression brouillon couverture 100% (sans TM) → PEC nettoyée."""
        # Nouveau SO avec police 100% pour n'avoir qu'une facture assurance
        order = self.env['sale.order'].create({
            'partner_id': self.patient.id,
            'policy_id': self.policy_full.id,
            'order_line': [
                Command.create({
                    'product_id': self.product_monture.id,
                    'product_uom_qty': 1,
                    'price_unit': 50000.0,
                }),
            ],
        })
        pec = self._approve_pec(order)
        pec.with_user(self.user_responsable).action_create_invoices()
        self.assertEqual(pec.state, 'invoiced')
        self.assertTrue(pec.invoice_insurance_id)
        self.assertFalse(pec.invoice_tm_id)

        ins_invoice = pec.invoice_insurance_id
        self.assertEqual(ins_invoice.state, 'draft')

        ins_invoice.unlink()

        self.assertEqual(pec.state, 'approved')
        self.assertFalse(pec.invoice_insurance_id)
        self.assertFalse(pec.invoice_tm_id)

    def test_unlink_normal_invoice_allowed(self):
        """Test non-suppression facture normale : unlink() réussit (NFR15)."""
        # Créer une facture normale (pas optique)
        normal_invoice = self.env['account.move'].create({
            'partner_id': self.patient.id,
            'move_type': 'out_invoice',
            'invoice_line_ids': [
                Command.create({
                    'product_id': self.product_monture.id,
                    'name': 'Monture standard',
                    'quantity': 1,
                    'price_unit': 50000.0,
                }),
            ],
        })
        # Doit pouvoir être supprimée sans erreur
        normal_invoice.unlink()

    def test_split_invoice_performance(self):
        """Test performance NFR4 : création complète < 3 secondes."""
        start = time.time()
        self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        duration = time.time() - start
        self.assertLess(duration, 3.0, "La création des factures split doit prendre moins de 3 secondes")

    def test_insurance_sent_default(self):
        """Test insurance_sent default : False par défaut sur facture assurance."""
        self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        ins_invoice = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
            ('is_insurance_invoice', '=', True),
        ])
        self.assertFalse(ins_invoice.insurance_sent)

    def test_tm_drives_invoice_status(self):
        """Test invoice_status : le TM patient pilote le statut 'facturé' de la commande."""
        self.sale_order.with_user(self.user_responsable).action_create_split_invoices()
        invoices = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.sale_order.id),
        ])
        tm_invoice = invoices.filtered('is_tm_invoice')
        ins_invoice = invoices.filtered('is_insurance_invoice')
        # Le TM doit être lié via sale_line_ids (pilote qty_invoiced)
        self.assertTrue(
            tm_invoice.invoice_line_ids.mapped('sale_line_ids'),
            "Les lignes TM doivent être liées aux lignes de commande via sale_line_ids",
        )
        # L'assurance ne doit PAS être liée via sale_line_ids
        self.assertFalse(
            ins_invoice.invoice_line_ids.mapped('sale_line_ids'),
            "Les lignes assurance ne doivent PAS être liées via sale_line_ids",
        )
        # La commande doit être considérée comme entièrement facturée
        self.assertEqual(
            self.sale_order.invoice_status,
            'invoiced',
            "La commande doit être 'Entièrement facturée' grâce au TM patient",
        )
        # Les deux factures doivent apparaître dans le smart button
        self.assertIn(tm_invoice, self.sale_order.invoice_ids)
        self.assertIn(ins_invoice, self.sale_order.invoice_ids)
