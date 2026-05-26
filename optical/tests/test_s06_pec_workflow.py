# -*- coding: utf-8 -*-
"""Tests d'intégration Story 6.2 — Facturation split via PEC approuvée et traçabilité."""
from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestPecInvoicing(OpticalTestCommon):
    """Tests du workflow PEC → facturation split (AC #1-#8)."""

    def _generate_invoices(self, pec):
        """Helper : génère les factures via le responsable."""
        return pec.with_user(self.user_responsable).action_create_invoices()

    def test_01_full_workflow_approved_to_invoiced(self):
        """AC#1 : workflow complet PEC approved → invoiced."""
        pec = self._approve_pec()
        self.assertEqual(pec.state, 'approved')

        # Générer les factures (en tant que responsable)
        self._generate_invoices(pec)
        self.assertEqual(pec.state, 'invoiced')
        self.assertTrue(pec.invoice_insurance_id)
        self.assertTrue(pec.invoice_tm_id)

    def test_02_invoice_amounts_integrity(self):
        """AC#5 : somme facture assurance + TM == total commande (NFR9)."""
        pec = self._approve_pec()
        self._generate_invoices(pec)

        ins_total = pec.invoice_insurance_id.amount_total
        tm_total = pec.invoice_tm_id.amount_total
        order_total = pec.sale_order_id.amount_total

        self.assertAlmostEqual(
            ins_total + tm_total, order_total, places=2,
            msg="La somme assurance + TM doit être égale au total commande (NFR9).",
        )

    def test_03_traceability_pec_and_order_on_invoices(self):
        """AC#2 : pec_id et insurance_sale_order_id renseignés sur les 2 factures (FR34, NFR11)."""
        pec = self._approve_pec()
        self._generate_invoices(pec)

        # Facture assurance
        ins = pec.invoice_insurance_id
        self.assertEqual(ins.pec_id, pec)
        self.assertEqual(ins.insurance_sale_order_id, pec.sale_order_id)
        self.assertEqual(ins.insurance_policy_id, pec.policy_id)
        self.assertTrue(ins.is_insurance_invoice)
        self.assertFalse(ins.is_tm_invoice)

        # Ticket modérateur
        tm = pec.invoice_tm_id
        self.assertEqual(tm.pec_id, pec)
        self.assertEqual(tm.insurance_sale_order_id, pec.sale_order_id)
        self.assertTrue(tm.is_tm_invoice)
        self.assertFalse(tm.is_insurance_invoice)

    def test_04_constraint_insurance_invoice_without_order(self):
        """AC#3 : facture is_insurance_invoice sans commande → ValidationError (NFR11)."""
        with self.assertRaises(ValidationError):
            self.env['account.move'].create({
                'partner_id': self.insurer.id,
                'move_type': 'out_invoice',
                'is_insurance_invoice': True,
                # insurance_sale_order_id intentionnellement absent
            })

    def test_05_constraint_non_optical_invoice_ok(self):
        """AC#3 NFR15 : facture standard sans pec_id → OK, pas d'erreur."""
        move = self.env['account.move'].create({
            'partner_id': self.patient.id,
            'move_type': 'out_invoice',
        })
        self.assertTrue(move)
        self.assertFalse(move.is_insurance_invoice)
        self.assertFalse(move.pec_id)

    def test_06_permission_vendeur_cannot_create_invoices(self):
        """AC#6 test permissions : vendeur ne peut pas générer les factures."""
        pec = self._approve_pec()
        with self.assertRaises(UserError):
            pec.with_user(self.user_vendeur).action_create_invoices()

    def test_08_double_invoicing_prevented(self):
        """AC#6 : PEC déjà facturée → tentative re-génération → erreur."""
        pec = self._approve_pec()
        self._generate_invoices(pec)
        self.assertEqual(pec.state, 'invoiced')

        with self.assertRaises(UserError):
            self._generate_invoices(pec)

    def test_09_invoice_lines_real_products(self):
        """AC#5 : lignes facture avec vrais produits proratisés (pas de libellé Acompte)."""
        pec = self._approve_pec()
        self._generate_invoices(pec)

        ins_lines = pec.invoice_insurance_id.invoice_line_ids.filtered(
            lambda l: l.product_id
        )
        tm_lines = pec.invoice_tm_id.invoice_line_ids.filtered(
            lambda l: l.product_id
        )

        # Vérifier que les produits réels sont utilisés
        ins_products = ins_lines.mapped('product_id')
        tm_products = tm_lines.mapped('product_id')
        self.assertIn(self.product_monture, ins_products)
        self.assertIn(self.product_verre, ins_products)
        self.assertIn(self.product_monture, tm_products)
        self.assertIn(self.product_verre, tm_products)

        # Vérifier que les libellés contiennent les noms de produits
        for line in ins_lines:
            self.assertIn(line.product_id.name, line.name)

    def test_11_sale_order_split_button_hidden_with_pec(self):
        """AC#7 : bouton split sur sale.order masqué si PEC existe."""
        order = self.sale_order
        order.policy_id = self.policy.id

        # Avant PEC : pec_count == 0
        self.assertEqual(order.pec_count, 0)

        # Après PEC : pec_count == 1
        order.action_create_pec()
        order.action_confirm()
        self.assertEqual(order.pec_count, 1)
        # Le champ pec_count > 0 rend le bouton invisible (testé via le domain XML)

    def test_12_sale_order_split_delegates_to_approved_pec(self):
        """AC#7 : action_create_split_invoices délègue à la PEC approuvée."""
        new_order = self.env['sale.order'].create({
            'partner_id': self.patient.id,
            'policy_id': self.policy.id,
            'order_line': [Command.create({
                'product_id': self.product_monture.id,
                'product_uom_qty': 1,
                'price_unit': 50000.0,
            })],
        })
        pec = self._approve_pec(new_order)
        self.assertEqual(pec.state, 'approved')

        # Le bouton split délègue à la PEC et fonctionne
        result = new_order.with_user(self.user_responsable).action_create_split_invoices()
        self.assertEqual(result['res_model'], 'account.move')
        self.assertEqual(pec.state, 'invoiced')

    def test_13_invoiced_state_prevents_invoice_creation(self):
        """AC#6 : PEC en état invoiced empêche la re-génération."""
        pec = self._approve_pec()
        self._generate_invoices(pec)
        self.assertEqual(pec.state, 'invoiced')

        # Tenter de regénérer échoue (state check before permission check)
        with self.assertRaises(UserError):
            self._generate_invoices(pec)

    def test_15_invoice_partners(self):
        """AC#1 : vérifier les partenaires sur les factures générées."""
        pec = self._approve_pec()
        self._generate_invoices(pec)

        # Facture assurance → partenaire = assureur/IPM
        self.assertEqual(pec.invoice_insurance_id.partner_id, self.insurer)
        # Ticket modérateur → partenaire = patient
        self.assertEqual(pec.invoice_tm_id.partner_id, self.patient)

    def test_16_chatter_message_on_invoicing(self):
        """AC#1 : message chatter posté après génération des factures."""
        pec = self._approve_pec()
        msg_count_before = len(pec.message_ids)
        self._generate_invoices(pec)
        msg_count_after = len(pec.message_ids)
        # Au moins un message (facturation) + un message tracking (state change)
        self.assertGreater(msg_count_after, msg_count_before)

    def test_17_only_approved_can_generate(self):
        """AC#1 : seule une PEC approuvée peut générer les factures."""
        pec = self._create_pec()
        self.assertEqual(pec.state, 'draft')
        with self.assertRaises(UserError):
            self._generate_invoices(pec)

        pec.action_submit()
        self.assertEqual(pec.state, 'submitted')
        with self.assertRaises(UserError):
            self._generate_invoices(pec)

    def test_19_tax_ids_inherited_from_order_lines(self):
        """CR#2 : les taxes des factures sont héritées de la commande, pas du produit."""
        company = self.env.company
        country = (
            company.account_fiscal_country_id
            or company.country_id
            or self.env['res.country'].search([], limit=1)
        )
        tax_18 = self.env['account.tax'].create({
            'name': 'TVA 18% Test',
            'type_tax_use': 'sale',
            'amount_type': 'percent',
            'amount': 18,
            'company_id': company.id,
            'country_id': country.id,
        })

        # Produit avec taxe par défaut
        product_taxed = self.env['product.product'].create({
            'name': 'Monture Taxée',
            'type': 'consu',
            'list_price': 60000.0,
            'taxes_id': [Command.set([tax_18.id])],
        })

        # Commande SANS taxes sur les lignes (on retire explicitement)
        order = self.env['sale.order'].create({
            'partner_id': self.patient.id,
            'policy_id': self.policy.id,
            'order_line': [Command.create({
                'product_id': product_taxed.id,
                'product_uom_qty': 1,
                'price_unit': 60000.0,
                'tax_id': [Command.set([])],
            })],
        })

        pec = self._approve_pec(order)
        self._generate_invoices(pec)

        # Les lignes facture NE doivent PAS avoir la taxe 18% du produit
        self.assertTrue(pec.invoice_tm_id, "TM attendu avec couverture partielle")
        ins_lines = pec.invoice_insurance_id.invoice_line_ids.filtered(lambda l: l.product_id)
        tm_lines = pec.invoice_tm_id.invoice_line_ids.filtered(lambda l: l.product_id)
        for line in ins_lines | tm_lines:
            self.assertNotIn(
                tax_18, line.tax_ids,
                "Les taxes doivent venir de la commande (vide), pas du produit.",
            )

    def test_20_tax_ids_preserved_from_order_lines(self):
        """CR#2 : si la commande a une taxe, les factures la portent aussi.

        NOTE: Ce test crée sa propre commande avec taxe explicite.
        """
        company = self.env.company
        country = (
            company.account_fiscal_country_id
            or company.country_id
            or self.env['res.country'].search([], limit=1)
        )
        tax_10 = self.env['account.tax'].create({
            'name': 'TVA 10% Test',
            'type_tax_use': 'sale',
            'amount_type': 'percent',
            'amount': 10,
            'company_id': company.id,
            'country_id': country.id,
        })

        product_no_tax = self.env['product.product'].create({
            'name': 'Verre Sans Taxe',
            'type': 'consu',
            'list_price': 40000.0,
            'taxes_id': [],
        })

        # Commande AVEC taxe 10% sur la ligne (produit n'a pas de taxe)
        order = self.env['sale.order'].create({
            'partner_id': self.patient.id,
            'policy_id': self.policy.id,
            'order_line': [Command.create({
                'product_id': product_no_tax.id,
                'product_uom_qty': 1,
                'price_unit': 40000.0,
                'tax_id': [Command.set([tax_10.id])],
            })],
        })

        pec = self._approve_pec(order)
        self._generate_invoices(pec)

        # Les lignes facture DOIVENT avoir la taxe 10% de la commande
        self.assertTrue(pec.invoice_tm_id, "TM attendu avec couverture partielle")
        ins_lines = pec.invoice_insurance_id.invoice_line_ids.filtered(lambda l: l.product_id)
        tm_lines = pec.invoice_tm_id.invoice_line_ids.filtered(lambda l: l.product_id)
        for line in ins_lines | tm_lines:
            self.assertIn(
                tax_10, line.tax_ids,
                "Les taxes de la commande doivent être propagées aux factures.",
            )

    def test_21_full_coverage_single_invoice(self):
        """AC#8 : couverture 100% → 1 seule facture assurance, pas de TM."""
        # Commande avec police couverture 100%
        order = self.env['sale.order'].create({
            'partner_id': self.patient.id,
            'policy_id': self.policy_full.id,
            'order_line': [
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
            ],
        })

        pec = self._approve_pec(order)
        self._generate_invoices(pec)

        # PEC doit être en état facturé
        self.assertEqual(pec.state, 'invoiced')

        # 1 seule facture assurance créée
        self.assertTrue(pec.invoice_insurance_id)
        self.assertFalse(pec.invoice_tm_id, "Pas de TM quand couverture 100%")

        # Montant assurance = total commande
        self.assertAlmostEqual(
            pec.invoice_insurance_id.amount_total,
            order.amount_total,
            places=2,
            msg="Facture assurance doit couvrir 100% du total commande (NFR9).",
        )

        # Partenaire = assureur
        self.assertEqual(pec.invoice_insurance_id.partner_id, self.insurer)

        # Traçabilité
        ins = pec.invoice_insurance_id
        self.assertEqual(ins.pec_id, pec)
        self.assertEqual(ins.insurance_sale_order_id, order)
        self.assertTrue(ins.is_insurance_invoice)

    def test_22_full_coverage_workflow_to_invoiced(self):
        """AC#8 : workflow complet couverture 100% jusqu'à facturation."""
        order = self.env['sale.order'].create({
            'partner_id': self.patient.id,
            'policy_id': self.policy_full.id,
            'order_line': [Command.create({
                'product_id': self.product_monture.id,
                'product_uom_qty': 1,
                'price_unit': 50000.0,
            })],
        })

        pec = self._approve_pec(order)
        result = self._generate_invoices(pec)

        # Action window : form view (1 seule facture)
        self.assertEqual(result.get('view_mode'), 'form')
        self.assertEqual(result.get('res_id'), pec.invoice_insurance_id.id)
        self.assertEqual(pec.state, 'invoiced')

    def test_23_create_pec_on_draft_order(self):
        """Story 6.5 AC#1+AC#2+AC#4 : workflow complet PEC sur SO draft (workflow réel opticien)."""
        order = self.env['sale.order'].create({
            'partner_id': self.patient.id,
            'policy_id': self.policy.id,
            'order_line': [
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
            ],
        })
        self.assertEqual(order.state, 'draft')

        # Créer PEC sur SO draft (confirm=False)
        pec = self._create_pec(order, confirm=False)
        self.assertEqual(pec.state, 'draft')
        self.assertEqual(order.state, 'draft')

        # Soumettre PEC sans confirmation SO
        pec.action_submit()
        self.assertEqual(pec.state, 'submitted')
        self.assertEqual(order.state, 'draft')

        # Approuver PEC
        pec.with_user(self.user_responsable).action_approve()
        self.assertEqual(pec.state, 'approved')

        # Facturation bloquée tant que SO non confirmé (AC#3)
        with self.assertRaises(UserError):
            self._generate_invoices(pec)

        # Confirmer le SO
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

        # Saisir le montant assurance approuvé puis facturer
        pec.write({'amount_insurance_approved': order.amount_insurance or order.amount_total})
        self._generate_invoices(pec)
        self.assertEqual(pec.state, 'invoiced')
        self.assertTrue(pec.invoice_insurance_id)
        self.assertTrue(pec.invoice_tm_id)

        # Intégrité comptable (NFR9)
        ins_total = pec.invoice_insurance_id.amount_total
        tm_total = pec.invoice_tm_id.amount_total
        self.assertAlmostEqual(
            ins_total + tm_total, order.amount_total, places=2,
        )

    def test_24_create_pec_on_cancelled_order_fails(self):
        """Story 6.5 AC#5 : SO annulé → erreur création PEC."""
        order = self.env['sale.order'].create({
            'partner_id': self.patient.id,
            'order_line': [Command.create({
                'product_id': self.product_monture.id,
                'product_uom_qty': 1,
                'price_unit': 50000.0,
            })],
        })
        # Confirmer sans police (pas de guard PEC), puis annuler
        order.action_confirm()
        order._action_cancel()
        self.assertEqual(order.state, 'cancel')

        # Assigner la police après annulation, puis tenter de créer PEC
        order.write({'policy_id': self.policy.id})
        with self.assertRaises(UserError):
            order.action_create_pec()

    def test_25_create_pec_on_sent_order(self):
        """Story 6.5 AC#1 review : workflow PEC sur SO en état sent (devis envoyé)."""
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
        # Simuler l'envoi du devis
        order.write({'state': 'sent'})
        self.assertEqual(order.state, 'sent')

        # Créer PEC sur SO sent
        order.action_create_pec()
        pec = order.pec_id
        self.assertTrue(pec)
        self.assertEqual(pec.state, 'draft')

        # Soumettre PEC
        pec.action_submit()
        self.assertEqual(pec.state, 'submitted')
