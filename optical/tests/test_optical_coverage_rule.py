# -*- coding: utf-8 -*-
from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestOpticalCoverageRule(OpticalTestCommon):
    """Tests pour le modèle optical.coverage.rule (Story 5.1)."""

    def test_create_rule(self):
        """Création d'une règle liée à un plan → succès."""
        rule = self.env['optical.coverage.rule'].create({
            'plan_id': self.plan.id,
            'product_category': 'accessory',
            'coverage_rate': 50.0,
        })
        self.assertTrue(rule.id)
        self.assertEqual(rule.plan_id, self.plan)
        self.assertEqual(rule.product_category, 'accessory')
        self.assertEqual(rule.coverage_rate, 50.0)

    def test_unique_category_per_plan(self):
        """Deux règles avec même catégorie sur même plan → IntegrityError."""
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.env['optical.coverage.rule'].create({
                'plan_id': self.plan.id,
                'product_category': 'frame',  # Already exists via common.py
                'coverage_rate': 60.0,
            })

    def test_coverage_rate_constraint_negative(self):
        """Taux hors plage (< 0) → ValidationError."""
        with self.assertRaises(ValidationError):
            self.env['optical.coverage.rule'].create({
                'plan_id': self.plan.id,
                'product_category': 'accessory',
                'coverage_rate': -10.0,
            })

    def test_coverage_rate_constraint_over_100(self):
        """Taux hors plage (> 100) → ValidationError."""
        with self.assertRaises(ValidationError):
            self.env['optical.coverage.rule'].create({
                'plan_id': self.plan.id,
                'product_category': 'accessory',
                'coverage_rate': 150.0,
            })

    def test_cascade_delete(self):
        """Suppression du plan → les règles sont supprimées en cascade."""
        plan = self.env['optical.insurer.plan'].create({
            'name': 'Plan Cascade Test',
            'insurer_id': self.insurer.id,
            'billing_mode': 'third_party',
        })
        rule = self.env['optical.coverage.rule'].create({
            'plan_id': plan.id,
            'product_category': 'frame',
            'coverage_rate': 70.0,
        })
        rule_id = rule.id
        plan.unlink()
        self.assertFalse(self.env['optical.coverage.rule'].browse(rule_id).exists())

    def test_rule_acl_vendeur(self):
        """Vendeur peut lire mais pas créer/modifier/supprimer."""
        rule = self.coverage_rule_frame.with_user(self.user_vendeur)
        rule.read(['coverage_rate'])

        with self.assertRaises(AccessError):
            self.env['optical.coverage.rule'].with_user(self.user_vendeur).create({
                'plan_id': self.plan.id,
                'product_category': 'accessory',
                'coverage_rate': 50.0,
            })

        with self.assertRaises(AccessError):
            rule.write({'coverage_rate': 60.0})

        with self.assertRaises(AccessError):
            rule.unlink()

    def test_rule_acl_manager(self):
        """Responsable peut créer/modifier/supprimer."""
        rule = self.env['optical.coverage.rule'].with_user(self.user_responsable).create({
            'plan_id': self.plan.id,
            'product_category': 'contact_lens',
            'coverage_rate': 65.0,
        })
        self.assertTrue(rule.id)
        rule.write({'coverage_rate': 70.0})
        self.assertEqual(rule.coverage_rate, 70.0)
        rule.unlink()
        self.assertFalse(rule.exists())
