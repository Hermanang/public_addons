# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import Command, fields as odoo_fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestOpticalPolicy(OpticalTestCommon):
    """Tests du modèle optical.policy."""

    def test_create_policy(self):
        """Création d'une police avec patient, assureur, taux."""
        self.assertTrue(self.policy.id)
        self.assertEqual(self.policy.patient_id, self.patient)
        self.assertEqual(self.policy.insurer_id, self.insurer)
        self.assertEqual(self.policy.coverage_rate, 80.0)
        self.assertEqual(self.policy.state, 'active')

    def test_unlink_raises_user_error(self):
        """La suppression d'une police lève UserError (NFR13)."""
        with self.assertRaises(UserError):
            self.policy.unlink()

    def test_check_dates_constraint(self):
        """date_end doit être postérieure à date_start."""
        with self.assertRaises(ValidationError):
            self.env['optical.policy'].create({
                'patient_id': self.patient.id,
                'insurer_id': self.insurer.id,
                'coverage_rate': 80.0,
                'date_start': '2026-06-01',
                'date_end': '2026-01-01',
            })

    def test_check_dates_equal_raises(self):
        """date_end == date_start doit aussi lever une erreur."""
        with self.assertRaises(ValidationError):
            self.env['optical.policy'].create({
                'patient_id': self.patient.id,
                'insurer_id': self.insurer.id,
                'coverage_rate': 80.0,
                'date_start': '2026-06-01',
                'date_end': '2026-06-01',
            })

    def test_vendeur_cannot_unlink_policy_acl(self):
        """Le vendeur n'a pas le droit de suppression (ACL perm_unlink=0)."""
        with self.assertRaises(AccessError):
            self.env['optical.policy'].with_user(self.user_vendeur).check_access_rights('unlink')

    def test_vendeur_unlink_blocked_by_override(self):
        """L'override unlink() bloque aussi la suppression avec UserError (NFR13)."""
        with self.assertRaises(UserError):
            self.policy.with_user(self.user_vendeur).unlink()

    def test_manager_full_crud(self):
        """Le responsable a le CRUD complet sur optical.policy."""
        # Create
        policy = self.env['optical.policy'].with_user(self.user_responsable).create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'coverage_rate': 60.0,
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',

        })
        self.assertTrue(policy.id)

        # Read
        policy_read = self.env['optical.policy'].with_user(self.user_responsable).browse(policy.id)
        self.assertEqual(policy_read.coverage_rate, 60.0)

        # Write
        policy_read.with_user(self.user_responsable).write({'coverage_rate': 90.0})
        self.assertEqual(policy_read.coverage_rate, 90.0)

        # Unlink — le UserError du override bloque toujours, mais
        # l'ACL manager autorise perm_unlink=1. On vérifie que c'est
        # bien le UserError métier et non un AccessError.
        with self.assertRaises(UserError):
            policy_read.with_user(self.user_responsable).unlink()

    def test_sequence_generated(self):
        """La référence est auto-générée via la séquence."""
        self.assertTrue(self.policy.name)
        self.assertNotEqual(self.policy.name, 'Nouveau')
        self.assertTrue(self.policy.name.startswith('POL/'))

    # --- Tests Story 5.2 : Souscripteur et relation bénéficiaire ---

    def test_create_policy_with_subscriber(self):
        """Création d'une police avec subscriber_id et beneficiary_relationship (FR20)."""
        self.assertEqual(self.policy.subscriber_id, self.subscriber)
        self.assertEqual(self.policy.beneficiary_relationship, 'holder')

    def test_beneficiary_relationship_values(self):
        """Toutes les valeurs du selection beneficiary_relationship sont valides (FR21)."""
        for value in ('holder', 'spouse', 'child', 'parent', 'other'):
            self.policy.write({'beneficiary_relationship': value})
            self.assertEqual(self.policy.beneficiary_relationship, value)

    def test_subscriber_optional(self):
        """Création d'une police sans subscriber_id — le champ est optionnel."""
        policy = self.env['optical.policy'].create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'coverage_rate': 80.0,
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',

        })
        self.assertFalse(policy.subscriber_id)
        self.assertTrue(policy.id)

    def test_member_number(self):
        """Création d'une police avec member_number — le champ est correctement enregistré."""
        self.policy.write({'member_number': 'ADH-2026-001'})
        self.assertEqual(self.policy.member_number, 'ADH-2026-001')

    def test_tracking_subscriber(self):
        """Les champs subscriber_id, beneficiary_relationship, member_number ont tracking=True (NFR16)."""
        fields_spec = self.env['optical.policy']._fields
        self.assertTrue(fields_spec['subscriber_id'].tracking)
        self.assertTrue(fields_spec['beneficiary_relationship'].tracking)
        self.assertTrue(fields_spec['member_number'].tracking)

    def test_unlink_blocked(self):
        """Suppression d'une police avec souscripteur lève UserError (NFR13)."""
        with self.assertRaises(UserError):
            self.policy.unlink()

    def test_policy_acl_vendeur(self):
        """Le vendeur peut créer/modifier une police avec les nouveaux champs."""
        policy = self.env['optical.policy'].with_user(self.user_vendeur).create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'subscriber_id': self.subscriber.id,
            'beneficiary_relationship': 'spouse',
            'member_number': 'ADH-V-001',
            'coverage_rate': 70.0,
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',

        })
        self.assertEqual(policy.subscriber_id, self.subscriber)
        self.assertEqual(policy.beneficiary_relationship, 'spouse')
        self.assertEqual(policy.member_number, 'ADH-V-001')
        # Write
        policy.with_user(self.user_vendeur).write({'beneficiary_relationship': 'child'})
        self.assertEqual(policy.beneficiary_relationship, 'child')

    def test_policy_acl_manager(self):
        """Le responsable a le CRUD complet avec les nouveaux champs."""
        policy = self.env['optical.policy'].with_user(self.user_responsable).create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'subscriber_id': self.subscriber.id,
            'beneficiary_relationship': 'parent',
            'member_number': 'ADH-M-001',
            'coverage_rate': 60.0,
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',

        })
        self.assertTrue(policy.id)
        # Read
        self.assertEqual(policy.subscriber_id, self.subscriber)
        # Write
        policy.with_user(self.user_responsable).write({'member_number': 'ADH-M-002'})
        self.assertEqual(policy.member_number, 'ADH-M-002')
        # Unlink blocked by override (UserError, not AccessError)
        with self.assertRaises(UserError):
            policy.with_user(self.user_responsable).unlink()

    # --- Tests Story 5.3 : Consommation automatique et expiration des polices ---

    def _create_insurance_invoice(self, policy, amount, state='posted', date=None):
        """Helper : crée une facture assurance liée à une police."""
        if date is None:
            date = odoo_fields.Date.context_today(self.env['account.move'])
        journal = self.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', policy.company_id.id),
        ], limit=1)
        # Confirmer la commande de test si nécessaire (traçabilité NFR11)
        if self.sale_order.state != 'sale':
            self.sale_order.action_confirm()
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': policy.insurer_id.id,
            'invoice_date': date,
            'date': date,
            'journal_id': journal.id,
            'is_insurance_invoice': True,
            'insurance_policy_id': policy.id,
            'insurance_sale_order_id': self.sale_order.id,
            'invoice_line_ids': [Command.create({
                'name': 'Ligne assurance test',
                'quantity': 1,
                'price_unit': amount,
            })],
        })
        if state == 'posted':
            move.action_post()
        return move

    def test_amount_consumed_no_invoices(self):
        """Police sans factures → amount_consumed = 0 (FR22)."""
        self.assertEqual(self.policy.amount_consumed, 0)

    def test_amount_consumed_with_posted_invoices(self):
        """Police avec factures validées → amount_consumed = somme correcte (FR22)."""
        self._create_insurance_invoice(self.policy, 50000)
        self._create_insurance_invoice(self.policy, 30000)
        self.policy.invalidate_recordset()
        self.assertEqual(self.policy.amount_consumed, 80000)

    def test_amount_consumed_excludes_draft_invoices(self):
        """Factures brouillon non comptées dans la consommation (FR22)."""
        self._create_insurance_invoice(self.policy, 50000, state='posted')
        self._create_insurance_invoice(self.policy, 20000, state='draft')
        self.policy.invalidate_recordset()
        self.assertEqual(self.policy.amount_consumed, 50000)

    def test_amount_consumed_excludes_other_year(self):
        """Factures d'une autre année non comptées (FR22)."""
        today = odoo_fields.Date.context_today(self.env['account.move'])
        last_year = today - relativedelta(years=1)
        self._create_insurance_invoice(self.policy, 50000, date=today)
        self._create_insurance_invoice(self.policy, 30000, date=last_year)
        self.policy.invalidate_recordset()
        self.assertEqual(self.policy.amount_consumed, 50000)

    def test_amount_remaining_correct(self):
        """amount_remaining = annual_cap_total - amount_consumed (FR22)."""
        self._create_insurance_invoice(self.policy, 100000)
        self.policy.invalidate_recordset()
        # annual_cap_total = 200000 (frame) + 300000 (lens) = 500000
        self.assertEqual(self.policy.annual_cap_total, 500000)
        self.assertEqual(self.policy.amount_remaining, 400000)

    def test_amount_remaining_no_cap(self):
        """Police sans plan → remaining = 0 (pas de plafond)."""
        policy_no_plan = self.env['optical.policy'].create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'coverage_rate': 80.0,
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',

        })
        self.assertEqual(policy_no_plan.annual_cap_total, 0)
        self.assertEqual(policy_no_plan.amount_remaining, 0)

    def test_cron_expires_active_past_date_end(self):
        """Cron expire les polices actives dont date_end est dépassée (FR23)."""
        policy_past = self.env['optical.policy'].create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'coverage_rate': 80.0,
            'date_start': '2025-01-01',
            'date_end': '2025-06-30',

        })
        self.assertEqual(policy_past.state, 'active')
        self.env['optical.policy']._cron_expire_policies()
        self.assertEqual(policy_past.state, 'expired')

    def test_cron_does_not_expire_future(self):
        """Cron n'expire pas les polices avec date_end future (FR23)."""
        self.assertEqual(self.policy.state, 'active')
        self.env['optical.policy']._cron_expire_policies()
        self.assertEqual(self.policy.state, 'active')

    def test_cron_does_not_expire_cancelled(self):
        """Cron n'expire pas les polices annulées (FR23)."""
        policy_cancelled = self.env['optical.policy'].create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'coverage_rate': 80.0,
            'date_start': '2025-01-01',
            'date_end': '2025-06-30',
            'state': 'cancelled',

        })
        self.env['optical.policy']._cron_expire_policies()
        self.assertEqual(policy_cancelled.state, 'cancelled')

    def test_cron_boundary_today(self):
        """Police avec date_end == today → NON expirée (dernier jour de validité) (FR23)."""
        today = odoo_fields.Date.context_today(self.env['optical.policy'])
        policy_today = self.env['optical.policy'].create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'coverage_rate': 80.0,
            'date_start': '2025-01-01',
            'date_end': str(today),

        })
        self.env['optical.policy']._cron_expire_policies()
        self.assertEqual(policy_today.state, 'active')

    def test_expired_policy_not_selectable_on_so(self):
        """Police expirée ne peut pas être sélectionnée sur un devis (AC #3)."""
        policy_expired = self.env['optical.policy'].create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'coverage_rate': 80.0,
            'date_start': '2025-01-01',
            'date_end': '2025-06-30',
            'state': 'expired',

        })
        with self.assertRaises(ValidationError):
            self.env['sale.order'].create({
                'partner_id': self.patient.id,
                'policy_id': policy_expired.id,
    

            })
