# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestOpticalInsurerPlan(OpticalTestCommon):
    """Tests pour le modèle optical.insurer.plan (Story 5.1)."""

    def test_create_plan(self):
        """Création d'un plan avec les champs requis → succès."""
        plan = self.env['optical.insurer.plan'].create({
            'name': 'Plan Test',
            'insurer_id': self.insurer.id,
            'default_coverage_rate': 75.0,
            'billing_mode': 'reimbursement',
        })
        self.assertTrue(plan.id)
        self.assertEqual(plan.name, 'Plan Test')
        self.assertEqual(plan.insurer_id, self.insurer)
        self.assertEqual(plan.default_coverage_rate, 75.0)
        self.assertEqual(plan.billing_mode, 'reimbursement')

    def test_coverage_rate_constraint_negative(self):
        """Taux < 0 → ValidationError."""
        with self.assertRaises(ValidationError):
            self.env['optical.insurer.plan'].create({
                'name': 'Plan Invalide',
                'insurer_id': self.insurer.id,
                'default_coverage_rate': -5.0,
                'billing_mode': 'third_party',
            })

    def test_coverage_rate_constraint_over_100(self):
        """Taux > 100 → ValidationError."""
        with self.assertRaises(ValidationError):
            self.env['optical.insurer.plan'].create({
                'name': 'Plan Invalide',
                'insurer_id': self.insurer.id,
                'default_coverage_rate': 101.0,
                'billing_mode': 'third_party',
            })

    def test_coverage_rate_boundary_values(self):
        """Taux 0% et 100% → succès (valeurs limites)."""
        plan_zero = self.env['optical.insurer.plan'].create({
            'name': 'Plan Zero',
            'insurer_id': self.insurer.id,
            'default_coverage_rate': 0.0,
            'billing_mode': 'third_party',
        })
        self.assertEqual(plan_zero.default_coverage_rate, 0.0)
        plan_full = self.env['optical.insurer.plan'].create({
            'name': 'Plan Full',
            'insurer_id': self.insurer.id,
            'default_coverage_rate': 100.0,
            'billing_mode': 'third_party',
        })
        self.assertEqual(plan_full.default_coverage_rate, 100.0)

    def test_display_name(self):
        """display_name contient le nom du plan et de l'assureur."""
        self.assertIn(self.plan.name, self.plan.display_name)
        self.assertIn(self.insurer.name, self.plan.display_name)

    def test_plan_acl_vendeur(self):
        """Vendeur peut lire mais pas créer/modifier/supprimer un plan."""
        # Lecture OK
        plan = self.plan.with_user(self.user_vendeur)
        plan.read(['name'])

        # Création KO
        with self.assertRaises(AccessError):
            self.env['optical.insurer.plan'].with_user(self.user_vendeur).create({
                'name': 'Plan Non Autorisé',
                'insurer_id': self.insurer.id,
                'default_coverage_rate': 80.0,
                'billing_mode': 'third_party',
            })

        # Écriture KO
        with self.assertRaises(AccessError):
            plan.write({'name': 'Modifié'})

        # Suppression KO
        with self.assertRaises(AccessError):
            plan.unlink()

    def test_plan_acl_manager(self):
        """Responsable peut créer/modifier un plan."""
        plan = self.env['optical.insurer.plan'].with_user(self.user_responsable).create({
            'name': 'Plan Manager',
            'insurer_id': self.insurer.id,
            'default_coverage_rate': 60.0,
            'billing_mode': 'reimbursement',

        })
        self.assertTrue(plan.id)
        plan.write({'name': 'Plan Manager Modifié'})
        self.assertEqual(plan.name, 'Plan Manager Modifié')

