# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestAgingReport(OpticalTestCommon):
    """Tests Story 7-2 : champs ancienneté et vues vieillissement créances."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Créer des factures via le workflow PEC → action_create_invoices
        pec = cls._approve_pec()
        pec.with_user(cls.user_responsable).action_create_invoices()
        pec.invalidate_recordset()

        # Récupérer les factures créées
        cls.insurance_invoice = cls.env['account.move'].search([
            ('pec_id', '=', pec.id),
            ('is_insurance_invoice', '=', True),
        ], limit=1)
        cls.tm_invoice = cls.env['account.move'].search([
            ('pec_id', '=', pec.id),
            ('is_tm_invoice', '=', True),
        ], limit=1)

    def test_days_overdue_45_days(self):
        """AC3 — days_overdue calcule correctement pour une facture de 45 jours."""
        today = fields.Date.context_today(self.env['account.move'])
        self.insurance_invoice.write({
            'invoice_date': today - timedelta(days=45),
        })
        self.insurance_invoice.invalidate_recordset(['days_overdue', 'aging_bucket'])
        self.assertEqual(self.insurance_invoice.days_overdue, 45)

    def test_aging_bucket_0_30(self):
        """AC4 — bucket '0_30' pour 15 jours."""
        today = fields.Date.context_today(self.env['account.move'])
        self.insurance_invoice.write({
            'invoice_date': today - timedelta(days=15),
        })
        self.insurance_invoice.invalidate_recordset(['days_overdue', 'aging_bucket'])
        self.assertEqual(self.insurance_invoice.aging_bucket, '0_30')
        self.assertEqual(self.insurance_invoice.days_overdue, 15)

    def test_aging_bucket_31_60(self):
        """AC4 — bucket '31_60' pour 45 jours."""
        today = fields.Date.context_today(self.env['account.move'])
        self.insurance_invoice.write({
            'invoice_date': today - timedelta(days=45),
        })
        self.insurance_invoice.invalidate_recordset(['days_overdue', 'aging_bucket'])
        self.assertEqual(self.insurance_invoice.aging_bucket, '31_60')

    def test_aging_bucket_61_90(self):
        """AC4 — bucket '61_90' pour 75 jours."""
        today = fields.Date.context_today(self.env['account.move'])
        self.insurance_invoice.write({
            'invoice_date': today - timedelta(days=75),
        })
        self.insurance_invoice.invalidate_recordset(['days_overdue', 'aging_bucket'])
        self.assertEqual(self.insurance_invoice.aging_bucket, '61_90')

    def test_aging_bucket_over_90(self):
        """AC4 — bucket 'over_90' pour 100 jours."""
        today = fields.Date.context_today(self.env['account.move'])
        self.insurance_invoice.write({
            'invoice_date': today - timedelta(days=100),
        })
        self.insurance_invoice.invalidate_recordset(['days_overdue', 'aging_bucket'])
        self.assertEqual(self.insurance_invoice.aging_bucket, 'over_90')

    def test_aging_bucket_boundary_30(self):
        """AC4 — frontière : exactement 30 jours → bucket '0_30'."""
        today = fields.Date.context_today(self.env['account.move'])
        self.insurance_invoice.write({'invoice_date': today - timedelta(days=30)})
        self.insurance_invoice.invalidate_recordset(['days_overdue', 'aging_bucket'])
        self.assertEqual(self.insurance_invoice.aging_bucket, '0_30')
        self.assertEqual(self.insurance_invoice.days_overdue, 30)

    def test_aging_bucket_boundary_31(self):
        """AC4 — frontière : exactement 31 jours → bucket '31_60'."""
        today = fields.Date.context_today(self.env['account.move'])
        self.insurance_invoice.write({'invoice_date': today - timedelta(days=31)})
        self.insurance_invoice.invalidate_recordset(['days_overdue', 'aging_bucket'])
        self.assertEqual(self.insurance_invoice.aging_bucket, '31_60')

    def test_aging_bucket_boundary_60(self):
        """AC4 — frontière : exactement 60 jours → bucket '31_60'."""
        today = fields.Date.context_today(self.env['account.move'])
        self.insurance_invoice.write({'invoice_date': today - timedelta(days=60)})
        self.insurance_invoice.invalidate_recordset(['days_overdue', 'aging_bucket'])
        self.assertEqual(self.insurance_invoice.aging_bucket, '31_60')

    def test_aging_bucket_boundary_61(self):
        """AC4 — frontière : exactement 61 jours → bucket '61_90'."""
        today = fields.Date.context_today(self.env['account.move'])
        self.insurance_invoice.write({'invoice_date': today - timedelta(days=61)})
        self.insurance_invoice.invalidate_recordset(['days_overdue', 'aging_bucket'])
        self.assertEqual(self.insurance_invoice.aging_bucket, '61_90')

    def test_aging_bucket_boundary_90(self):
        """AC4 — frontière : exactement 90 jours → bucket '61_90'."""
        today = fields.Date.context_today(self.env['account.move'])
        self.insurance_invoice.write({'invoice_date': today - timedelta(days=90)})
        self.insurance_invoice.invalidate_recordset(['days_overdue', 'aging_bucket'])
        self.assertEqual(self.insurance_invoice.aging_bucket, '61_90')

    def test_aging_bucket_boundary_91(self):
        """AC4 — frontière : exactement 91 jours → bucket 'over_90'."""
        today = fields.Date.context_today(self.env['account.move'])
        self.insurance_invoice.write({'invoice_date': today - timedelta(days=91)})
        self.insurance_invoice.invalidate_recordset(['days_overdue', 'aging_bucket'])
        self.assertEqual(self.insurance_invoice.aging_bucket, 'over_90')

    def test_days_overdue_no_date(self):
        """AC3 — days_overdue == 0 si invoice_date est False."""
        self.insurance_invoice.write({'invoice_date': False})
        self.insurance_invoice.invalidate_recordset(['days_overdue', 'aging_bucket'])
        self.assertEqual(self.insurance_invoice.days_overdue, 0)

    def test_aging_action_domain(self):
        """AC5 — Le domain de l'action vieillissement filtre correctement."""
        self.assertTrue(self.insurance_invoice, "La facture assurance doit exister")
        today = fields.Date.context_today(self.env['account.move'])
        self.insurance_invoice.write({
            'invoice_date': today - timedelta(days=45),
        })
        # Poster la facture pour qu'elle soit visible dans la vue
        self.insurance_invoice.action_post()

        domain = [
            ('is_insurance_invoice', '=', True),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
        ]
        results = self.env['account.move'].search(domain)
        self.assertIn(self.insurance_invoice, results)
        # Le TM ne doit PAS apparaître dans les créances IPM
        self.assertTrue(self.tm_invoice, "La facture TM doit exister")
        self.assertNotIn(self.tm_invoice, results)

    def test_tm_domain_filter(self):
        """AC6 — Les TM sont correctement filtrés par le domain TM."""
        self.assertTrue(self.tm_invoice, "La facture TM doit exister")
        domain = [
            ('is_tm_invoice', '=', True),
            ('move_type', '=', 'out_invoice'),
        ]
        results = self.env['account.move'].search(domain)
        self.assertIn(self.tm_invoice, results)
        # La facture assurance ne doit PAS apparaître dans les TM
        self.assertNotIn(self.insurance_invoice, results)

    def test_non_regression_non_insurance(self):
        """NFR15 — Les factures non-assurance ne sont pas affectées."""
        # Créer une facture client standard (non optique)
        partner = self.env['res.partner'].create({'name': 'Client Standard'})
        standard_invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_date': fields.Date.context_today(self.env['account.move']) - timedelta(days=60),
            'invoice_line_ids': [(0, 0, {
                'name': 'Service standard',
                'quantity': 1,
                'price_unit': 10000.0,
            })],
        })
        # Le champ days_overdue fonctionne aussi sur les factures normales (c'est un champ sur account.move)
        self.assertEqual(standard_invoice.days_overdue, 60)
        self.assertEqual(standard_invoice.aging_bucket, '31_60')
        # Mais elle ne doit PAS apparaître dans le domain vieillissement IPM
        domain = [
            ('is_insurance_invoice', '=', True),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
        ]
        results = self.env['account.move'].search(domain)
        self.assertNotIn(standard_invoice, results)

    def test_vendeur_can_read_aging_fields(self):
        """L1 — Le vendeur peut lire les champs ancienneté."""
        today = fields.Date.context_today(self.env['account.move'])
        self.insurance_invoice.write({
            'invoice_date': today - timedelta(days=45),
        })
        invoice_as_vendeur = self.insurance_invoice.with_user(self.user_vendeur)
        invoice_as_vendeur.invalidate_recordset(['days_overdue', 'aging_bucket'])
        self.assertEqual(invoice_as_vendeur.days_overdue, 45)
        self.assertEqual(invoice_as_vendeur.aging_bucket, '31_60')

    def test_search_aging_bucket_domain(self):
        """L3 — La méthode _search_aging_bucket traduit correctement les domains."""
        today = fields.Date.context_today(self.env['account.move'])
        self.insurance_invoice.write({
            'invoice_date': today - timedelta(days=45),
        })
        # Recherche par domain aging_bucket
        results = self.env['account.move'].search([
            ('aging_bucket', '=', '31_60'),
            ('id', '=', self.insurance_invoice.id),
        ])
        self.assertIn(self.insurance_invoice, results)
        # Ne doit pas apparaître dans un autre bucket
        results_wrong = self.env['account.move'].search([
            ('aging_bucket', '=', '0_30'),
            ('id', '=', self.insurance_invoice.id),
        ])
        self.assertNotIn(self.insurance_invoice, results_wrong)
