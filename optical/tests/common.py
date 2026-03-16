# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import Command
from odoo.fields import Date
from odoo.tests import tagged, TransactionCase


@tagged('post_install', '-at_install')
class OpticalTestCommon(TransactionCase):
    """Classe de base pour les tests du module Optique."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Groupes de securite
        cls.group_optical_user = cls.env.ref('optical.group_optical_user')
        cls.group_optical_manager = cls.env.ref('optical.group_optical_manager')

        # Groupe OU (conditionnel : présent si bridge optical_operating_unit installé)
        group_all_ou = cls.env.ref(
            'operating_unit_access_all.group_all_operating_unit',
            raise_if_not_found=False,
        )

        # Groupes de base pour les utilisateurs de test
        base_groups = [
            cls.env.ref('base.group_user').id,
            cls.env.ref('sales_team.group_sale_salesman').id,
        ]
        if group_all_ou:
            base_groups.append(group_all_ou.id)

        # Utilisateur Vendeur Optique (avec droits vente pour accès sale.order)
        cls.user_vendeur = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Vendeur Test',
            'login': 'vendeur_test',
            'email': 'vendeur@test.com',
            'groups_id': [Command.set([
                cls.group_optical_user.id,
            ] + base_groups)],
        })

        # Utilisateur Responsable Optique (accès toutes ventes + manager optique)
        cls.user_responsable = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Responsable Test',
            'login': 'responsable_test',
            'email': 'responsable@test.com',
            'groups_id': [Command.set([
                cls.group_optical_manager.id,
                cls.env.ref('sales_team.group_sale_salesman_all_leads').id,
            ] + base_groups)],
        })

        # Utilisateur sans groupe optique
        cls.user_sans_groupe = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Utilisateur Standard',
            'login': 'standard_test',
            'email': 'standard@test.com',
            'groups_id': [Command.set([
                cls.env.ref('base.group_user').id,
            ])],
        })

        # --- Données Story 2.1 + 3.2 : Patients ---
        today = Date.context_today(cls.env['res.partner'])
        cls.patient = cls.env['res.partner'].create({
            'name': 'Patient Test',
            'is_patient': True,
            'birthdate': today - relativedelta(years=30),
        })
        cls.patient_minor = cls.env['res.partner'].create({
            'name': 'Patient Mineur Test',
            'is_patient': True,
            'birthdate': today - relativedelta(years=10),
        })
        cls.patient_no_birthdate = cls.env['res.partner'].create({
            'name': 'Patient Sans Date Naissance',
            'is_patient': True,
            'birthdate': False,
        })
        cls.insurer = cls.env['res.partner'].create({
            'name': 'IPM Test',
            'is_insurer': True,
        })
        # --- Données Story 5.2 : Souscripteur ---
        cls.subscriber = cls.env['res.partner'].create({
            'name': 'Entreprise Souscripteur Test',
            'is_company': True,
        })
        # --- Données Story 5.1 : Plan de couverture et règles ---
        cls.plan = cls.env['optical.insurer.plan'].create({
            'name': 'Plan CNAM Standard',
            'insurer_id': cls.insurer.id,
            'default_coverage_rate': 80.0,
            'billing_mode': 'third_party',
        })
        cls.coverage_rule_frame = cls.env['optical.coverage.rule'].create({
            'plan_id': cls.plan.id,
            'product_category': 'frame',
            'coverage_rate': 70.0,
            'reference_price': 50000,
            'annual_ceiling': 200000,
        })
        cls.coverage_rule_lens = cls.env['optical.coverage.rule'].create({
            'plan_id': cls.plan.id,
            'product_category': 'lens',
            'coverage_rate': 90.0,
            'annual_ceiling': 300000,
        })
        cls.policy = cls.env['optical.policy'].create({
            'patient_id': cls.patient.id,
            'insurer_id': cls.insurer.id,
            'coverage_rate': 80.0,
            'plan_id': cls.plan.id,
            'subscriber_id': cls.subscriber.id,
            'beneficiary_relationship': 'holder',
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',
        })
        # --- Plan couverture 100 % (utilisé par Story 6.2, CC 6.6) ---
        cls.plan_full = cls.env['optical.insurer.plan'].create({
            'name': 'Plan Couverture Totale',
            'insurer_id': cls.insurer.id,
            'default_coverage_rate': 100.0,
            'billing_mode': 'third_party',
        })
        cls.env['optical.coverage.rule'].create({
            'plan_id': cls.plan_full.id,
            'product_category': 'frame',
            'coverage_rate': 100.0,
        })
        cls.env['optical.coverage.rule'].create({
            'plan_id': cls.plan_full.id,
            'product_category': 'lens',
            'coverage_rate': 100.0,
        })
        cls.policy_full = cls.env['optical.policy'].create({
            'patient_id': cls.patient.id,
            'insurer_id': cls.insurer.id,
            'coverage_rate': 100.0,
            'plan_id': cls.plan_full.id,
            'subscriber_id': cls.subscriber.id,
            'beneficiary_relationship': 'holder',
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',
        })

        # --- Données Story 3.1 : Prescripteur et Ordonnance ---
        cls.prescriber = cls.env['res.partner'].create({
            'name': 'Dr. Ndiaye',
            'is_prescriber': True,
            'prescriber_registration': 'MED-12345',
            'prescriber_specialty': 'ophthalmologist',
        })
        cls.prescription = cls.env['optical.prescription'].create({
            'patient_id': cls.patient.id,
            'prescriber_id': cls.prescriber.id,
            'od_sphere': 2.50,
            'od_cylinder': -1.25,
            'od_axis': 90,
            'od_addition': 1.50,
            'og_sphere': 3.00,
            'og_cylinder': -0.75,
            'og_axis': 85,
            'og_addition': 1.50,
            'od_pd': 32.0,
            'og_pd': 31.5,
            'pd_total': 63.5,
        })

        # --- Données Story 3.3 : Ordonnance confirmée pour liaison commande ---
        cls.prescription_confirmed = cls.env['optical.prescription'].create({
            'patient_id': cls.patient.id,
            'prescriber_id': cls.prescriber.id,
            'od_sphere': 2.50,
            'od_cylinder': -1.25,
            'od_axis': 90,
            'od_addition': 1.50,
            'og_sphere': 3.00,
            'og_cylinder': -0.75,
            'og_axis': 85,
            'og_addition': 1.50,
            'od_pd': 32.0,
            'og_pd': 31.5,
            'pd_total': 63.5,
            'notes': 'Port permanent',
        })
        cls.prescription_confirmed.action_confirm()

        # --- Données Story 2.2 : Produits et devis de test ---
        cls.product_monture = cls.env['product.product'].create({
            'name': 'Monture Test RAYBAN',
            'type': 'consu',
            'list_price': 50000.0,
            'taxes_id': [],
        })
        cls.product_verre = cls.env['product.product'].create({
            'name': 'Verre Test Progressif',
            'type': 'consu',
            'list_price': 30000.0,
            'taxes_id': [],
        })
        cls.sale_order = cls.env['sale.order'].create({
            'partner_id': cls.patient.id,
            'order_line': [
                Command.create({
                    'product_id': cls.product_monture.id,
                    'product_uom_qty': 1,
                    'price_unit': 50000.0,
                }),
                Command.create({
                    'product_id': cls.product_verre.id,
                    'product_uom_qty': 1,
                    'price_unit': 30000.0,
                }),
            ],
        })

    @classmethod
    def _confirm_sale_order(cls, order=None):
        """Helper : confirme la commande de test et la retourne."""
        order = order or cls.sale_order
        order.action_confirm()
        return order

    @classmethod
    def _create_pec(cls, order=None, confirm=True):
        """Helper : assigne la police et crée une PEC.

        Crée la PEC sur SO draft (workflow réel opticien), puis confirme si demandé.
        """
        order = order or cls.sale_order
        if not order.policy_id:
            order.policy_id = cls.policy.id
        order.action_create_pec()
        if confirm and order.state != 'sale':
            order.action_confirm()
        return order.pec_id

    @classmethod
    def _approve_pec(cls, order=None, confirm=True):
        """Helper : crée une PEC, la soumet et l'approuve. Retourne la PEC."""
        pec = cls._create_pec(order, confirm=confirm)
        pec.action_submit()
        pec.with_user(cls.user_responsable).action_approve()
        return pec
