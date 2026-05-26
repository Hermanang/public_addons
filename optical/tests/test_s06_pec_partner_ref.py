# -*- coding: utf-8 -*-
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestPecPartnerRef(OpticalTestCommon):
    """Tests pour le champ partner_ref sur optical.pec (Story 6-7)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pec = cls._create_pec()

    def test_partner_ref_stored(self):
        """AC1 : partner_ref est stocke en base apres saisie."""
        self.pec.partner_ref = 'IPM-2026-0042'
        self.pec.flush_recordset(['partner_ref'])
        self.pec.invalidate_recordset(['partner_ref'])
        self.assertEqual(self.pec.partner_ref, 'IPM-2026-0042')

    def test_partner_ref_display_name(self):
        """AC2 : display_name inclut partner_ref entre parentheses."""
        self.pec.partner_ref = 'IPM-2026-0042'
        self.pec.invalidate_recordset(['display_name'])
        expected = '%s (IPM-2026-0042)' % self.pec.name
        self.assertEqual(self.pec.display_name, expected)

    def test_partner_ref_display_name_empty(self):
        """AC3 : display_name sans parentheses vides quand partner_ref est vide."""
        self.pec.partner_ref = False
        self.pec.invalidate_recordset(['display_name'])
        self.assertEqual(self.pec.display_name, self.pec.name)
        self.assertNotIn('(', self.pec.display_name)

    def test_partner_ref_rec_names_search(self):
        """AC4 : recherche par partner_ref via name_search."""
        self.pec.partner_ref = 'IPM-2026-0042'
        results = self.env['optical.pec'].name_search('IPM-2026')
        result_ids = [r[0] for r in results]
        self.assertIn(self.pec.id, result_ids)

    def test_partner_ref_copy_false(self):
        """AC5 : copy() ne copie pas partner_ref."""
        self.pec.partner_ref = 'IPM-2026-0042'
        # Creer un nouveau SO pour eviter la contrainte unique
        new_order = self.env['sale.order'].create({
            'partner_id': self.patient.id,
            'policy_id': self.policy.id,
            'order_line': [(0, 0, {
                'product_id': self.product_monture.id,
                'product_uom_qty': 1,
                'price_unit': 50000.0,
            })],
        })
        # Copier la PEC avec un nouveau sale_order_id (sans PEC sur new_order)
        copy = self.pec.copy({'sale_order_id': new_order.id})
        self.assertFalse(copy.partner_ref)

    def test_partner_ref_related_on_invoice(self):
        """AC6 : pec_partner_ref visible sur les factures generées."""
        # Creer un nouveau SO pour cette PEC (evite la contrainte unique)
        order = self.env['sale.order'].create({
            'partner_id': self.patient.id,
            'policy_id': self.policy.id,
            'order_line': [(0, 0, {
                'product_id': self.product_monture.id,
                'product_uom_qty': 1,
                'price_unit': 50000.0,
            })],
        })
        order.action_create_pec()
        order.action_confirm()
        pec = order.pec_id
        pec.partner_ref = 'MUT-REF-123'
        # Utiliser le workflow reel (actions business, pas de write direct)
        pec.action_submit()
        pec_mgr = pec.with_user(self.user_responsable).sudo()
        pec_mgr.action_approve()
        pec.write({'amount_insurance_approved': order.amount_insurance or order.amount_total})
        pec_mgr.action_create_invoices()
        self.assertTrue(pec.invoice_insurance_id)
        self.assertEqual(pec.invoice_insurance_id.pec_partner_ref, 'MUT-REF-123')
