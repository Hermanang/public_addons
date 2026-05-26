# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import UserError
from odoo.fields import Date
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestInsuranceTracking(OpticalTestCommon):
    """Tests Story 7-1 : Vues suivi factures assurance et marquage envoi."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Créer des factures assurance + TM via le workflow PEC complet
        pec = cls._approve_pec()
        pec.with_user(cls.user_responsable).action_create_invoices()
        cls.pec = pec
        cls.invoice_insurance = pec.invoice_insurance_id
        cls.invoice_tm = pec.invoice_tm_id
        # Poster (valider) les factures pour les tests de marquage
        cls.invoice_insurance.action_post()
        cls.invoice_tm.action_post()

    # --- Task 1 : Champ insurance_sent_date et méthodes d'action ---

    def test_insurance_sent_date_default_false(self):
        """Le champ insurance_sent_date est vide par défaut."""
        self.assertFalse(self.invoice_insurance.insurance_sent_date)

    def test_mark_insurance_sent_sets_fields(self):
        """Le marquage envoi met insurance_sent=True et insurance_sent_date=today."""
        self.invoice_insurance.with_user(self.user_responsable).action_mark_insurance_sent()
        self.assertTrue(self.invoice_insurance.insurance_sent)
        self.assertEqual(self.invoice_insurance.insurance_sent_date, Date.today())

    def test_mark_insurance_sent_posts_chatter(self):
        """Le marquage envoi crée un message dans le chatter (NFR16)."""
        msg_count_before = len(self.invoice_insurance.message_ids)
        self.invoice_insurance.with_user(self.user_responsable).action_mark_insurance_sent()
        self.assertGreater(len(self.invoice_insurance.message_ids), msg_count_before)

    def test_unmark_insurance_sent(self):
        """L'annulation du marquage remet insurance_sent=False et insurance_sent_date=False."""
        self.invoice_insurance.with_user(self.user_responsable).action_mark_insurance_sent()
        self.invoice_insurance.with_user(self.user_responsable).action_unmark_insurance_sent()
        self.assertFalse(self.invoice_insurance.insurance_sent)
        self.assertFalse(self.invoice_insurance.insurance_sent_date)

    def test_mark_insurance_sent_multi(self):
        """Le marquage groupé fonctionne sur plusieurs factures."""
        # Créer une 2e commande + PEC + factures
        order2 = self.env['sale.order'].create({
            'partner_id': self.patient.id,
            'policy_id': self.policy.id,
            'order_line': [
                Command.create({
                    'product_id': self.product_monture.id,
                    'product_uom_qty': 1,
                    'price_unit': 40000.0,
                }),
            ],
        })
        order2.action_create_pec()
        order2.action_confirm()
        pec2 = order2.pec_id
        pec2.action_submit()
        pec2.with_user(self.user_responsable).action_approve()
        pec2.write({'amount_insurance_approved': order2.amount_insurance or order2.amount_total})
        pec2.with_user(self.user_responsable).action_create_invoices()
        invoice2 = pec2.invoice_insurance_id
        invoice2.action_post()

        invoices = self.invoice_insurance | invoice2
        invoices.with_user(self.user_responsable).action_mark_insurance_sent()
        for inv in invoices:
            self.assertTrue(inv.insurance_sent)
            self.assertEqual(inv.insurance_sent_date, Date.today())

    # --- Task 1 : Sécurité (AC6) ---

    def test_vendeur_cannot_mark_sent(self):
        """Un vendeur ne peut pas marquer les factures comme envoyées."""
        with self.assertRaises(UserError):
            self.invoice_insurance.with_user(self.user_vendeur).action_mark_insurance_sent()

    def test_vendeur_cannot_unmark_sent(self):
        """Un vendeur ne peut pas annuler le marquage."""
        self.invoice_insurance.with_user(self.user_responsable).action_mark_insurance_sent()
        with self.assertRaises(UserError):
            self.invoice_insurance.with_user(self.user_vendeur).action_unmark_insurance_sent()

    # --- Task 1 : Non-régression ---

    def test_non_insurance_invoice_not_affected(self):
        """Les factures non-assurance ne sont pas affectées par le marquage."""
        self.assertFalse(self.invoice_tm.is_insurance_invoice)
        with self.assertRaises(UserError):
            self.invoice_tm.with_user(self.user_responsable).action_mark_insurance_sent()

    # --- Task 6.6 : Domain actions ---

    def test_action_insurance_domain(self):
        """L'action factures assurance filtre correctement par is_insurance_invoice."""
        action = self.env.ref('optical.action_optical_insurance_invoices')
        self.assertEqual(
            action.domain,
            "[('is_insurance_invoice', '=', True), ('move_type', '=', 'out_invoice')]",
        )

    def test_action_tm_domain(self):
        """L'action tickets modérateurs filtre correctement par is_tm_invoice."""
        action = self.env.ref('optical.action_optical_tm_invoices')
        self.assertEqual(
            action.domain,
            "[('is_tm_invoice', '=', True), ('move_type', '=', 'out_invoice')]",
        )

    # --- Code review : idempotence et intégrité ---

    def test_mark_sent_idempotent_preserves_date(self):
        """Re-appeler action_mark_insurance_sent sur une facture déjà marquée préserve la date originale."""
        self.invoice_insurance.with_user(self.user_responsable).action_mark_insurance_sent()
        original_date = self.invoice_insurance.insurance_sent_date
        self.assertTrue(original_date)
        # Simuler un 2e appel (groupé ou accidentel)
        self.invoice_insurance.with_user(self.user_responsable).action_mark_insurance_sent()
        self.assertEqual(self.invoice_insurance.insurance_sent_date, original_date)

    def test_insurance_invoice_partner_is_insurer(self):
        """La facture assurance a l'assureur comme partner_id."""
        self.assertEqual(self.invoice_insurance.partner_id, self.insurer)

    def test_tm_invoice_partner_is_patient(self):
        """Le ticket modérateur a le patient comme partner_id."""
        self.assertEqual(self.invoice_tm.partner_id, self.patient)

    # --- Task 1 : Non-régression (suite) ---

    def test_mark_only_posted_invoices(self):
        """Seules les factures validées (posted) peuvent être marquées comme envoyées."""
        # Créer une facture assurance en draft via une nouvelle PEC
        order3 = self.env['sale.order'].create({
            'partner_id': self.patient.id,
            'policy_id': self.policy.id,
            'order_line': [
                Command.create({
                    'product_id': self.product_verre.id,
                    'product_uom_qty': 1,
                    'price_unit': 25000.0,
                }),
            ],
        })
        order3.action_create_pec()
        order3.action_confirm()
        pec3 = order3.pec_id
        pec3.action_submit()
        pec3.with_user(self.user_responsable).action_approve()
        pec3.write({'amount_insurance_approved': order3.amount_insurance or order3.amount_total})
        pec3.with_user(self.user_responsable).action_create_invoices()
        draft_insurance = pec3.invoice_insurance_id
        # La facture est en draft — ne PAS poster
        self.assertEqual(draft_insurance.state, 'draft')
        with self.assertRaises(UserError):
            draft_insurance.with_user(self.user_responsable).action_mark_insurance_sent()
