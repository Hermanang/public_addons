# -*- coding: utf-8 -*-
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import Command
from odoo.tests import tagged

from odoo.addons.optical.tests.common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestGiftExclusion(OpticalTestCommon):
    """Tests pour le module bridge optical_gift_exclusion."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Produit promo (simule un cadeau/offert)
        cls.product_promo = cls.env['product.product'].create({
            'name': 'Promo Cadeau Test',
            'type': 'consu',
            'list_price': 5000.0,
            'taxes_id': [],
        })

    def _create_order_with_gift(self, policy=None, gift_price=5000.0):
        """Cree un SO avec lignes normales + une ligne cadeau (is_gift=True)."""
        policy = policy or self.policy
        order = self.env['sale.order'].create({
            'partner_id': self.patient.id,
            'policy_id': policy.id,
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
                Command.create({
                    'product_id': self.product_promo.id,
                    'product_uom_qty': 1,
                    'price_unit': gift_price,
                    'is_gift': True,
                }),
            ],
        })
        return order

    def _create_order_no_gift(self, policy=None):
        """Cree un SO avec uniquement des lignes normales (pas de cadeau)."""
        policy = policy or self.policy
        order = self.env['sale.order'].create({
            'partner_id': self.patient.id,
            'policy_id': policy.id,
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
        return order

    def _pec_flow(self, order):
        """Cree PEC -> confirme SO -> soumet -> approuve -> facture. Retourne la PEC."""
        order.action_create_pec()
        order.action_confirm()
        pec = order.pec_id
        pec.action_submit()
        pec.with_user(self.user_responsable).action_approve()
        pec.with_user(self.user_responsable).action_create_invoices()
        return pec

    # ========================================================================
    # Tests cadeau manuel (approche hybride) — Story 14.1 refactor
    # ========================================================================

    def test_manual_gift_on_so_line(self):
        """Cocher is_gift sur une SO line marque la ligne comme cadeau."""
        order = self._create_order_with_gift()
        gift_lines = order.order_line.filtered('is_gift')
        self.assertEqual(len(gift_lines), 1)
        self.assertEqual(gift_lines[0].product_id, self.product_promo)

    def test_sale_loyalty_sync_is_reward_to_is_gift(self):
        """Si is_reward_line est positionne via write(), is_gift est synchronise."""
        # Ce test valide la synchro sale_loyalty -> is_gift
        # is_reward_line existe seulement si sale_loyalty est installe
        if 'is_reward_line' not in self.env['sale.order.line']._fields:
            self.skipTest("sale_loyalty non installe — synchro non applicable")
        order = self._create_order_no_gift()
        line = order.order_line.sorted('id')[0]
        self.assertFalse(line.is_gift)
        line.write({'is_reward_line': True})
        self.assertTrue(line.is_gift, "is_gift doit etre synchronise depuis is_reward_line")

    # ========================================================================
    # Tests propagation SO line → facture — Story 14.1
    # ========================================================================

    # --- AC#3 : SO avec cadeau → PEC → is_gift=True ---
    def test_pec_gift_lines_marked_is_gift(self):
        """Les lignes facture assurance correspondant aux SO lines cadeau ont is_gift=True."""
        order = self._create_order_with_gift()
        pec = self._pec_flow(order)

        insurance_inv = pec.invoice_insurance_id
        self.assertTrue(insurance_inv, "La facture assurance doit exister")

        inv_lines = insurance_inv.invoice_line_ids.sorted('id')
        self.assertEqual(len(inv_lines), 3, "3 lignes produit attendues")
        self.assertFalse(inv_lines[0].is_gift, "Monture ne doit pas etre is_gift")
        self.assertFalse(inv_lines[1].is_gift, "Verre ne doit pas etre is_gift")
        self.assertTrue(inv_lines[2].is_gift, "Ligne cadeau doit etre is_gift")

    # --- AC#3 bis : is_gift aussi sur la facture TM (ticket moderateur) ---
    def test_pec_gift_lines_marked_is_gift_tm(self):
        """Les lignes facture TM correspondant aux SO lines cadeau ont is_gift=True."""
        order = self._create_order_with_gift()
        pec = self._pec_flow(order)

        tm_inv = pec.invoice_tm_id
        self.assertTrue(tm_inv, "La facture TM doit exister (couverture 80%)")

        inv_lines = tm_inv.invoice_line_ids.sorted('id')
        self.assertEqual(len(inv_lines), 3, "3 lignes produit attendues sur TM")
        self.assertFalse(inv_lines[0].is_gift, "Monture TM ne doit pas etre is_gift")
        self.assertFalse(inv_lines[1].is_gift, "Verre TM ne doit pas etre is_gift")
        self.assertTrue(inv_lines[2].is_gift, "Ligne cadeau TM doit etre is_gift")

    # --- AC#4 : SO sans cadeau → toutes is_gift=False ---
    def test_pec_no_gift_all_is_gift_false(self):
        """Toutes les lignes facture assurance ont is_gift=False sans cadeau."""
        order = self._create_order_no_gift()
        pec = self._pec_flow(order)

        insurance_inv = pec.invoice_insurance_id
        inv_lines = insurance_inv.invoice_line_ids
        self.assertTrue(len(inv_lines) >= 2, "Au moins 2 lignes produit attendues")
        for line in inv_lines:
            self.assertFalse(line.is_gift, "Aucune ligne ne doit etre is_gift")

    # --- AC#3+4 mix : SO avec mix cadeau + normal → bon marquage ---
    def test_pec_mixed_lines_correct_marking(self):
        """Un SO avec mix de lignes normales et cadeau marque correctement chaque ligne."""
        order = self._create_order_with_gift()
        pec = self._pec_flow(order)

        insurance_inv = pec.invoice_insurance_id
        inv_lines = insurance_inv.invoice_line_ids.sorted('id')

        gift_lines = inv_lines.filtered('is_gift')
        normal_lines = inv_lines.filtered(lambda l: not l.is_gift)
        self.assertEqual(len(gift_lines), 1, "Une seule ligne doit etre is_gift")
        self.assertEqual(len(normal_lines), 2, "Deux lignes normales attendues")
        self.assertEqual(gift_lines[0].product_id, self.product_promo)

    # --- AC#5 bis : Chemin delegation SO → PEC via action_create_split_invoices ---
    def test_split_invoices_with_pec_delegates_is_gift(self):
        """Via action_create_split_invoices avec PEC approuvee, la delegation propage is_gift."""
        order = self._create_order_with_gift()
        order.action_create_pec()
        order.action_confirm()
        pec = order.pec_id
        pec.action_submit()
        pec.with_user(self.user_responsable).action_approve()

        # Appeler via le chemin SO (qui delegue a PEC)
        order.with_user(self.user_responsable).action_create_split_invoices()

        insurance_inv = pec.invoice_insurance_id
        self.assertTrue(insurance_inv, "La facture assurance doit exister via delegation")

        inv_lines = insurance_inv.invoice_line_ids.sorted('id')
        gift_lines = inv_lines.filtered('is_gift')
        self.assertEqual(len(gift_lines), 1, "Une seule ligne doit etre is_gift via delegation")
        self.assertEqual(gift_lines[0].product_id, self.product_promo)

    # ========================================================================
    # Tests bordereau (Story 14.2) — filtrage is_gift
    # ========================================================================

    def _create_claim_sheet_with_gift(self):
        """Helper : cree un bordereau contenant une facture avec mix normal + cadeau.

        Retourne (claim_sheet, insurance_invoice).
        """
        order = self._create_order_with_gift()
        pec = self._pec_flow(order)
        insurance_inv = pec.invoice_insurance_id
        insurance_inv.action_post()

        # Creer le bordereau via le wizard
        wizard = self.env['optical.claim.sheet.wizard'].with_user(
            self.user_responsable
        ).create({
            'insurer_id': self.insurer.id,
            'date_from': insurance_inv.invoice_date.replace(day=1),
            'date_to': (insurance_inv.invoice_date.replace(day=1) + relativedelta(months=1)) - timedelta(days=1),
        })
        wizard.action_search_invoices()
        wizard.action_generate()

        claim_sheet = insurance_inv.claim_sheet_id
        self.assertTrue(claim_sheet, "Le bordereau doit exister")
        return claim_sheet, insurance_inv

    # --- AC#3 : _get_tax_summary exclut les lignes is_gift ---
    def test_tax_summary_excludes_gift_lines(self):
        """La ventilation fiscale exclut les lignes is_gift=True."""
        claim_sheet, insurance_inv = self._create_claim_sheet_with_gift()

        # Verifier qu'on a bien des lignes is_gift sur la facture
        gift_lines = insurance_inv.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product' and l.is_gift
        )
        self.assertTrue(gift_lines, "Au moins une ligne is_gift doit exister")

        # Total des lignes normales (non-gift) seulement
        normal_lines = insurance_inv.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product' and not l.is_gift
        )
        expected_total = sum(normal_lines.mapped('price_total'))

        tax_summary = claim_sheet._get_tax_summary()

        # Le total de la ventilation fiscale doit correspondre aux lignes normales
        self.assertAlmostEqual(
            tax_summary['amount_total'], expected_total, places=2,
            msg="Le total fiscal doit exclure les lignes is_gift"
        )

    # --- AC#2 : _get_invoices_grouped subtotals excluent is_gift ---
    def test_invoices_grouped_subtotal_excludes_gift(self):
        """Les sous-totaux par groupe excluent les lignes is_gift."""
        claim_sheet, insurance_inv = self._create_claim_sheet_with_gift()

        groups = claim_sheet._get_invoices_grouped()
        self.assertTrue(groups, "Au moins un groupe doit exister")

        # Total des lignes normales (non-gift)
        normal_lines = insurance_inv.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product' and not l.is_gift
        )
        expected_subtotal = sum(normal_lines.mapped('price_total'))

        # Le subtotal du groupe doit etre hors cadeaux
        total_subtotals = sum(g['subtotal'] for g in groups)
        self.assertAlmostEqual(
            total_subtotals, expected_subtotal, places=2,
            msg="Le sous-total doit exclure les lignes is_gift"
        )

    # --- AC#4 : sans lignes is_gift, comportement inchange ---
    def test_bordereau_no_gift_lines_unchanged(self):
        """Sans lignes is_gift, le bordereau se comporte comme la base."""
        order = self._create_order_no_gift()
        pec = self._pec_flow(order)
        insurance_inv = pec.invoice_insurance_id
        insurance_inv.action_post()

        wizard = self.env['optical.claim.sheet.wizard'].with_user(
            self.user_responsable
        ).create({
            'insurer_id': self.insurer.id,
            'date_from': insurance_inv.invoice_date.replace(day=1),
            'date_to': (insurance_inv.invoice_date.replace(day=1) + relativedelta(months=1)) - timedelta(days=1),
        })
        wizard.action_search_invoices()
        wizard.action_generate()

        claim_sheet = insurance_inv.claim_sheet_id
        self.assertTrue(claim_sheet)

        # Toutes les lignes sont non-gift
        all_lines = insurance_inv.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product'
        )
        expected_total = sum(all_lines.mapped('price_total'))

        tax_summary = claim_sheet._get_tax_summary()
        self.assertAlmostEqual(
            tax_summary['amount_total'], expected_total, places=2,
            msg="Sans cadeaux, le total doit etre identique au montant total"
        )

        groups = claim_sheet._get_invoices_grouped()
        total_subtotals = sum(g['subtotal'] for g in groups)
        self.assertAlmostEqual(
            total_subtotals, expected_total, places=2,
            msg="Sans cadeaux, le sous-total doit correspondre au total"
        )

    # --- AC#5 : facture avec uniquement des lignes is_gift → subtotal = 0 ---
    def test_bordereau_all_gift_lines_subtotal_zero(self):
        """Un bordereau avec uniquement des lignes is_gift a un subtotal de 0."""
        # Creer une commande ou toutes les lignes sont cadeau
        order = self.env['sale.order'].create({
            'partner_id': self.patient.id,
            'policy_id': self.policy.id,
            'order_line': [
                Command.create({
                    'product_id': self.product_promo.id,
                    'product_uom_qty': 1,
                    'price_unit': 5000.0,
                    'is_gift': True,
                }),
            ],
        })

        pec = self._pec_flow(order)
        insurance_inv = pec.invoice_insurance_id
        insurance_inv.action_post()

        # Verifier que toutes les lignes produit sont is_gift
        product_lines = insurance_inv.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product'
        )
        self.assertTrue(
            all(l.is_gift for l in product_lines),
            "Toutes les lignes produit doivent etre is_gift"
        )

        wizard = self.env['optical.claim.sheet.wizard'].with_user(
            self.user_responsable
        ).create({
            'insurer_id': self.insurer.id,
            'date_from': insurance_inv.invoice_date.replace(day=1),
            'date_to': (insurance_inv.invoice_date.replace(day=1) + relativedelta(months=1)) - timedelta(days=1),
        })
        wizard.action_search_invoices()
        wizard.action_generate()

        claim_sheet = insurance_inv.claim_sheet_id
        self.assertTrue(claim_sheet)

        # Tax summary doit avoir un total de 0
        tax_summary = claim_sheet._get_tax_summary()
        self.assertAlmostEqual(
            tax_summary['amount_total'], 0.0, places=2,
            msg="Le total fiscal doit etre 0 quand toutes les lignes sont is_gift"
        )

        # Subtotals des groupes doivent etre 0
        groups = claim_sheet._get_invoices_grouped()
        for group in groups:
            self.assertAlmostEqual(
                group['subtotal'], 0.0, places=2,
                msg="Le sous-total du groupe doit etre 0"
            )

    # --- AC#1 : _amount_to_text avec montant hors cadeaux ---
    def test_amount_to_text_excludes_gift(self):
        """_amount_to_text() renvoie le montant hors cadeaux en lettres."""
        claim_sheet, _ = self._create_claim_sheet_with_gift()
        tax_summary = claim_sheet._get_tax_summary()

        text = claim_sheet._amount_to_text(tax_summary['amount_total'])
        self.assertIn("FRANCS CFA", text)

        # Le montant en lettres doit correspondre au total hors cadeaux
        text_zero = claim_sheet._amount_to_text(0)
        self.assertEqual(text_zero, "ZERO FRANC CFA")

    # ========================================================================
    # Tests propagation (Story 14.1) — chemin direct sans PEC
    # ========================================================================

    def test_split_invoices_no_pec_gift_marked(self):
        """Via action_create_split_invoices (chemin direct, sans PEC), is_gift est propage."""
        # Creer et confirmer le SO sans police pour eviter le blocage PEC
        order = self.env['sale.order'].create({
            'partner_id': self.patient.id,
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
                Command.create({
                    'product_id': self.product_promo.id,
                    'product_uom_qty': 1,
                    'price_unit': 5000.0,
                    'is_gift': True,
                }),
            ],
        })

        order.action_confirm()

        # Assigner police apres confirmation pour acceder au chemin direct
        order.write({'policy_id': self.policy.id})

        order.action_create_split_invoices()

        # Trouver la facture assurance creee
        insurance_inv = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', order.id),
            ('is_insurance_invoice', '=', True),
        ], limit=1)
        self.assertTrue(insurance_inv, "La facture assurance doit exister")

        inv_lines = insurance_inv.invoice_line_ids.sorted('id')

        # Verifier que les lignes cadeau sont marquées is_gift
        gift_lines = inv_lines.filtered('is_gift')
        normal_lines = inv_lines.filtered(lambda l: not l.is_gift)
        self.assertEqual(len(gift_lines), 1, "Une seule ligne doit etre is_gift")
        self.assertTrue(len(normal_lines) >= 1, "Au moins une ligne non-gift attendue")
        self.assertEqual(gift_lines[0].product_id, self.product_promo)
