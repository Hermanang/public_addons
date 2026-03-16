# -*- coding: utf-8 -*-
from odoo import Command
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestNFR15NonIntrusion(OpticalTestCommon):
    """Test de non-intrusion : le module optical ne doit pas alterer
    les workflows standard d'Odoo (NFR15, AC #6)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.has_chart = bool(cls.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1))

        cls.partner = cls.env['res.partner'].create({
            'name': 'Client Test Standard',
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Produit Test Standard',
            'type': 'consu',
            'list_price': 100.0,
            'invoice_policy': 'order',
        })

    def test_standard_sale_confirmation_unaltered(self):
        """Creer et confirmer une vente standard — le workflow natif
        doit fonctionner sans erreur (NFR15, AC #6)."""
        sale_order = self.env['sale.order'].sudo().create({
            'partner_id': self.partner.id,
            'order_line': [Command.create({
                'product_id': self.product.id,
                'product_uom_qty': 2,
                'price_unit': 100.0,
            })],
        })
        sale_order.action_confirm()
        self.assertEqual(
            sale_order.state, 'sale',
            "La commande doit passer en etat 'sale' apres confirmation"
        )

    def test_standard_sale_invoicing_unaltered(self):
        """La facturation standard produit une facture unique normale (NFR15, AC #6).
        Prerequis : un plan comptable doit etre configure."""
        if not self.has_chart:
            self.skipTest("Pas de plan comptable — facturation non testable")

        sale_order = self.env['sale.order'].sudo().create({
            'partner_id': self.partner.id,
            'order_line': [Command.create({
                'product_id': self.product.id,
                'product_uom_qty': 2,
                'price_unit': 100.0,
            })],
        })
        sale_order.action_confirm()
        invoice = sale_order._create_invoices()
        self.assertTrue(invoice, "La facture doit etre creee sans erreur")
        self.assertEqual(len(invoice), 1, "Une seule facture doit etre generee")
        self.assertEqual(
            invoice.move_type, 'out_invoice',
            "La facture doit etre de type 'out_invoice'"
        )

    def test_standard_sale_no_optical_fields_interference(self):
        """Les champs standard de sale.order ne sont pas modifies par le module optical."""
        sale_fields = self.env['sale.order'].fields_get()
        optical_fields = [f for f in sale_fields if f.startswith('optical_') or f.startswith('x_optical_')]
        self.assertEqual(
            len(optical_fields), 0,
            "Aucun champ optical ne doit etre ajoute a sale.order dans cette story"
        )
