# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestOpticalPec(OpticalTestCommon):
    """Tests du modèle optical.pec — Story 6.1."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Commande avec police (draft — PEC requise avant confirmation)
        cls.sale_order.policy_id = cls.policy.id

    # --- Task 1 : Création PEC ---

    def test_create_pec_from_confirmed_order(self):
        """PEC créée avec les bons liens (SO, police, patient, assureur)."""
        self.sale_order.action_create_pec()
        pec = self.sale_order.pec_id
        self.assertTrue(pec)
        self.assertEqual(pec.sale_order_id, self.sale_order)
        self.assertEqual(pec.policy_id, self.policy)
        self.assertEqual(pec.patient_id, self.patient)
        self.assertEqual(pec.insurer_id, self.insurer)
        self.assertEqual(pec.state, 'draft')
        self.assertTrue(pec.date_create)

    def test_pec_auto_sequence(self):
        """Le name est généré automatiquement via la séquence PEC/xxxxx."""
        self.sale_order.action_create_pec()
        pec = self.sale_order.pec_id
        self.assertTrue(pec.name.startswith('PEC/'))

    def test_pec_unique_per_order(self):
        """2e PEC sur même commande → erreur."""
        self.sale_order.action_create_pec()
        with self.assertRaises(UserError):
            self.sale_order.action_create_pec()

    def test_pec_amounts_from_order(self):
        """Les montants PEC sont correctement reliés à la commande."""
        self.sale_order.action_create_pec()
        pec = self.sale_order.pec_id
        self.assertEqual(pec.amount_total, self.sale_order.amount_total)
        self.assertEqual(pec.amount_insurance, self.sale_order.amount_insurance)
        self.assertEqual(pec.amount_patient, self.sale_order.amount_patient)

    # --- Task 2 : Workflow ---

    def test_pec_workflow_draft_to_submitted(self):
        """action_submit change l'état de draft à submitted."""
        self.sale_order.action_create_pec()
        pec = self.sale_order.pec_id
        pec.action_submit()
        self.assertEqual(pec.state, 'submitted')

    def test_pec_workflow_submitted_to_approved(self):
        """action_approve change l'état et renseigne date_approved."""
        self.sale_order.action_create_pec()
        pec = self.sale_order.pec_id
        pec.action_submit()
        pec.with_user(self.user_responsable).action_approve()
        self.assertEqual(pec.state, 'approved')
        self.assertTrue(pec.date_approved)

    def test_pec_workflow_submitted_to_refused(self):
        """action_refuse change l'état à refused."""
        self.sale_order.action_create_pec()
        pec = self.sale_order.pec_id
        pec.action_submit()
        pec.with_user(self.user_responsable).action_refuse()
        self.assertEqual(pec.state, 'refused')

    def test_pec_workflow_refused_to_draft(self):
        """action_reset_draft remet une PEC refusée en brouillon (FR33)."""
        self.sale_order.action_create_pec()
        pec = self.sale_order.pec_id
        pec.action_submit()
        pec.with_user(self.user_responsable).action_refuse()
        pec.with_user(self.user_responsable).action_reset_draft()
        self.assertEqual(pec.state, 'draft')
        self.assertFalse(pec.date_approved)

    # --- Validations d'état ---

    def test_pec_submit_on_draft_order_ok(self):
        """Story 6.5 : soumission autorisée même si SO en draft (workflow réel opticien)."""
        order2 = self.env['sale.order'].create({
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
        self.assertEqual(order2.state, 'draft')
        order2.action_create_pec()
        pec2 = order2.pec_id
        pec2.action_submit()
        self.assertEqual(pec2.state, 'submitted')

    def test_pec_submit_requires_active_policy(self):
        """Soumission bloquée si police expirée."""
        self.sale_order.action_create_pec()
        pec = self.sale_order.pec_id
        # Forcer la police à expired
        self.policy.write({'state': 'expired'})
        with self.assertRaises(UserError):
            pec.action_submit()
        # Restaurer
        self.policy.write({'state': 'active'})

    # --- Permissions ---

    def test_pec_approve_requires_manager(self):
        """Vendeur ne peut pas approuver une PEC."""
        self.sale_order.action_create_pec()
        pec = self.sale_order.pec_id
        pec.action_submit()
        with self.assertRaises(UserError):
            pec.with_user(self.user_vendeur).action_approve()

    def test_pec_refuse_requires_manager(self):
        """Vendeur ne peut pas refuser une PEC."""
        self.sale_order.action_create_pec()
        pec = self.sale_order.pec_id
        pec.action_submit()
        with self.assertRaises(UserError):
            pec.with_user(self.user_vendeur).action_refuse()

    # --- NFR13 : Non-suppression ---

    def test_pec_unlink_forbidden(self):
        """Suppression physique interdite (NFR13)."""
        self.sale_order.action_create_pec()
        pec = self.sale_order.pec_id
        with self.assertRaises(UserError):
            pec.unlink()

    # --- NFR16 : Chatter ---

    def test_pec_chatter_tracking(self):
        """Le champ state a tracking=True et le modèle hérite mail.thread (NFR16)."""
        pec_model = self.env['optical.pec']
        # Vérifier que le modèle hérite de mail.thread (via mail.thread.main.attachment)
        self.assertTrue(pec_model._mail_post_access,
                        "Le modèle PEC doit hériter de mail.thread pour le chatter.")
        # Vérifier que le champ state a tracking=True
        self.assertTrue(pec_model._fields['state'].tracking,
                        "Le champ state doit avoir tracking=True pour le suivi chatter.")

    # --- Validation création PEC ---

    def test_create_pec_on_draft_order_ok(self):
        """Story 6.5 : création PEC autorisée sur SO draft (workflow réel opticien)."""
        order2 = self.env['sale.order'].create({
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
        self.assertEqual(order2.state, 'draft')
        order2.action_create_pec()
        pec = order2.pec_id
        self.assertTrue(pec)
        self.assertEqual(pec.state, 'draft')
        self.assertEqual(pec.sale_order_id, order2)

    def test_create_pec_requires_active_policy(self):
        """Création PEC bloquée si police non active (M2)."""
        # Forcer la police à expired
        self.policy.write({'state': 'expired'})
        with self.assertRaises(UserError):
            self.sale_order.action_create_pec()
        # Restaurer
        self.policy.write({'state': 'active'})
