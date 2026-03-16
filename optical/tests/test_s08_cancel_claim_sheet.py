# -*- coding: utf-8 -*-
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import Command
from odoo.exceptions import UserError
from odoo.fields import Date
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestCancelClaimSheet(OpticalTestCommon):
    """Tests Story 8-4 : Annulation bordereau et libération factures."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.insurer.insurer_type = 'ipm'
        cls.product_monture.product_tmpl_id.optical_type = 'frame'
        cls.product_verre.product_tmpl_id.optical_type = 'lens'

        # Créer des factures assurance via le workflow PEC complet
        pec = cls._approve_pec()
        pec.with_user(cls.user_responsable).action_create_invoices()
        cls.pec = pec
        cls.invoice_insurance = pec.invoice_insurance_id
        cls.invoice_insurance.action_post()

        # Générer un bordereau
        wizard = cls.env['optical.claim.sheet.wizard'].with_user(
            cls.user_responsable
        ).create({
            'insurer_id': cls.insurer.id,
            'date_from': cls.invoice_insurance.invoice_date.replace(day=1),
            'date_to': (cls.invoice_insurance.invoice_date.replace(day=1) + relativedelta(months=1)) - timedelta(days=1),
        })
        wizard.action_search_invoices()
        wizard.action_generate()
        cls.claim_sheet = cls.invoice_insurance.claim_sheet_id

    # --- Task 4.1 : Test annulation réussie ---

    def test_cancel_success_state_and_invoices(self):
        """Annulation réussie : state=cancelled + factures libérées."""
        self.assertEqual(self.claim_sheet.state, 'generated')
        self.assertTrue(self.invoice_insurance.insurance_sent)
        self.assertTrue(self.invoice_insurance.claim_sheet_id)

        self.claim_sheet.with_user(self.user_responsable).action_cancel()

        self.assertEqual(self.claim_sheet.state, 'cancelled')
        # Factures libérées
        self.assertFalse(self.invoice_insurance.insurance_sent)
        self.assertFalse(self.invoice_insurance.insurance_sent_date)
        self.assertFalse(self.invoice_insurance.claim_sheet_id)

    def test_cancel_posts_chatter_message(self):
        """L'annulation poste un message dans le chatter du bordereau."""
        messages_before = len(self.claim_sheet.message_ids)
        self.claim_sheet.with_user(self.user_responsable).action_cancel()
        self.assertGreater(
            len(self.claim_sheet.message_ids), messages_before,
            "Un message doit être posté dans le chatter après annulation"
        )

    # --- Task 4.2 : Test blocage si amount_paid > 0 ---

    def test_cancel_blocked_if_paid(self):
        """UserError si on tente d'annuler un bordereau avec paiements reçus."""
        # Configurer le journal bancaire pour paiement direct
        bank_journal = self.env['account.journal'].search(
            [('type', '=', 'bank'), ('company_id', '=', self.env.company.id)],
            limit=1,
        )
        for method_line in bank_journal.inbound_payment_method_line_ids:
            method_line.payment_account_id = bank_journal.default_account_id

        # Payer la facture
        ctx = {
            'active_model': 'account.move',
            'active_ids': self.invoice_insurance.ids,
        }
        payment_wizard = self.env['account.payment.register'].with_context(
            **ctx
        ).create({'journal_id': bank_journal.id})
        payment_wizard._create_payments()
        self.claim_sheet.invalidate_recordset()

        self.assertGreater(self.claim_sheet.amount_paid, 0)
        with self.assertRaises(UserError):
            self.claim_sheet.with_user(self.user_responsable).action_cancel()

    # --- Task 4.3 : Test factures redeviennent eligibles ---

    def test_invoices_eligible_after_cancel(self):
        """Après annulation, les factures redeviennent éligibles pour un nouveau bordereau."""
        self.claim_sheet.with_user(self.user_responsable).action_cancel()

        # Re-générer un bordereau pour le même assureur/période
        wizard = self.env['optical.claim.sheet.wizard'].with_user(
            self.user_responsable
        ).create({
            'insurer_id': self.insurer.id,
            'date_from': self.invoice_insurance.invoice_date.replace(day=1),
            'date_to': (self.invoice_insurance.invoice_date.replace(day=1) + relativedelta(months=1)) - timedelta(days=1),
        })
        wizard.action_search_invoices()
        self.assertIn(
            self.invoice_insurance, wizard.invoice_ids,
            "Les factures libérées doivent être éligibles dans le wizard"
        )

    # --- Task 4.4 : Test retrocompatibilite ---

    def test_existing_claim_sheets_default_generated(self):
        """Les bordereaux existants ont state='generated' par défaut."""
        self.assertEqual(self.claim_sheet.state, 'generated')

    # --- Tests supplémentaires sécurité ---

    def test_cancel_vendeur_blocked(self):
        """Un vendeur ne peut pas annuler un bordereau (UserError)."""
        with self.assertRaises(UserError):
            self.claim_sheet.with_user(self.user_vendeur).action_cancel()

    def test_cancel_already_cancelled_blocked(self):
        """Annuler un bordereau déjà annulé lève UserError."""
        self.claim_sheet.with_user(self.user_responsable).action_cancel()
        with self.assertRaises(UserError):
            self.claim_sheet.with_user(self.user_responsable).action_cancel()
