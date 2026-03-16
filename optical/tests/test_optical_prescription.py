# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Date
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestOpticalPrescription(OpticalTestCommon):
    """Tests du modele optical.prescription (Story 3.1)."""

    def test_create_prescription(self):
        """Creation d'une ordonnance en brouillon avec mesures."""
        rx = self.prescription
        self.assertEqual(rx.state, 'draft')
        self.assertEqual(rx.patient_id, self.patient)
        self.assertEqual(rx.prescriber_id, self.prescriber)
        self.assertAlmostEqual(rx.od_sphere, 2.50)
        self.assertAlmostEqual(rx.od_cylinder, -1.25)
        self.assertEqual(rx.od_axis, 90)
        self.assertAlmostEqual(rx.od_addition, 1.50)
        self.assertAlmostEqual(rx.og_sphere, 3.00)
        self.assertAlmostEqual(rx.og_cylinder, -0.75)
        self.assertEqual(rx.og_axis, 85)
        self.assertAlmostEqual(rx.og_addition, 1.50)
        self.assertAlmostEqual(rx.od_pd, 32.0)
        self.assertAlmostEqual(rx.og_pd, 31.5)
        self.assertAlmostEqual(rx.pd_total, 63.5)

    def test_confirm(self):
        """Confirmer une ordonnance → state == 'confirmed' (FR9)."""
        self.prescription.action_confirm()
        self.assertEqual(self.prescription.state, 'confirmed')

    def test_confirm_without_patient(self):
        """Confirmer sans patient → UserError."""
        rx = self.env['optical.prescription'].new({
            'prescriber_id': self.prescriber.id,
        })
        with self.assertRaises(UserError):
            rx.action_confirm()

    def test_confirm_without_prescriber(self):
        """Confirmer sans prescripteur → UserError."""
        rx = self.env['optical.prescription'].new({
            'patient_id': self.patient.id,
        })
        with self.assertRaises(UserError):
            rx.action_confirm()

    def test_date_expiry(self):
        """Date d'expiration = date + 3 ans (FR10)."""
        today = Date.context_today(self.prescription)
        rx = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'date': today,
        })
        expected_expiry = today + relativedelta(years=3)
        self.assertEqual(rx.date_expiry, expected_expiry)

    def test_unlink_forbidden(self):
        """Suppression interdite → UserError (NFR13)."""
        with self.assertRaises(UserError):
            self.prescription.unlink()

    def test_sequence_name(self):
        """Le nom genere commence par 'ORD/' (NFR12)."""
        self.assertTrue(
            self.prescription.name.startswith('ORD/'),
            f"Le nom '{self.prescription.name}' devrait commencer par 'ORD/'"
        )

    def test_reset_to_draft(self):
        """Confirmer puis reset → state == 'draft'."""
        self.prescription.action_confirm()
        self.assertEqual(self.prescription.state, 'confirmed')
        self.prescription.action_reset_to_draft()
        self.assertEqual(self.prescription.state, 'draft')

    def test_reset_expired_forbidden(self):
        """Ordonnance expiree → reset → UserError."""
        self.prescription.state = 'expired'
        with self.assertRaises(UserError):
            self.prescription.action_reset_to_draft()

    def test_chatter_inheritance(self):
        """Le modele herite de mail.thread.main.attachment."""
        parents = self.env['optical.prescription']._inherit
        self.assertIn('mail.thread.main.attachment', parents)
        self.assertIn('mail.activity.mixin', parents)

    def test_acl_vendeur_crud(self):
        """Vendeur peut creer/lire/modifier une ordonnance."""
        Prescription = self.env['optical.prescription'].with_user(self.user_vendeur)
        # Lecture
        rx = Prescription.browse(self.prescription.id)
        rx.read(['name'])
        # Creation
        new_rx = Prescription.create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
        })
        self.assertTrue(new_rx.id)
        # Modification
        new_rx.write({'notes': 'Test vendeur'})

    def test_acl_vendeur_no_unlink_permission(self):
        """Vendeur n'a pas la permission de suppression (perm_unlink=0, FR53)."""
        # L'override unlink() bloque avec UserError avant que l'ACL ne soit verifiee.
        # On verifie que l'ACL aussi interdit la suppression via check_access_rights.
        Prescription = self.env['optical.prescription'].with_user(self.user_vendeur)
        with self.assertRaises(AccessError):
            Prescription.check_access_rights('unlink')

    def test_acl_manager_unlink_blocked_by_model(self):
        """Manager a la permission ACL de supprimer mais le modele le bloque (NFR13)."""
        Prescription = self.env['optical.prescription'].with_user(self.user_responsable)
        # L'ACL autorise unlink pour le manager
        Prescription.check_access_rights('unlink')
        # Mais le model.unlink() override bloque quand meme
        with self.assertRaises(UserError):
            Prescription.browse(self.prescription.id).unlink()

    def test_acl_sans_groupe(self):
        """Utilisateur sans groupe optique → AccessError sur lecture."""
        Prescription = self.env['optical.prescription'].with_user(self.user_sans_groupe)
        with self.assertRaises(AccessError):
            Prescription.search([])

    def test_archivage(self):
        """Archiver (active=False) au lieu de supprimer → succes."""
        self.prescription.active = False
        self.assertFalse(self.prescription.active)
        # L'ordonnance est archivee mais existe toujours
        rx = self.env['optical.prescription'].with_context(active_test=False).browse(self.prescription.id)
        self.assertTrue(rx.exists())


@tagged('post_install', '-at_install')
class TestPrescriptionExpiry(OpticalTestCommon):
    """Tests Story 3.2 : Expiration ordonnances et validation mesures."""

    # --- Tests expiration adulte/mineur (AC #1, #2, #5) ---

    def test_expiry_adult(self):
        """Ordonnance patient adulte (>= 16 ans) → expiration a 3 ans (FR10)."""
        today = Date.context_today(self.env['optical.prescription'])
        rx = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'date': today,
        })
        self.assertEqual(rx.date_expiry, today + relativedelta(years=3))

    def test_expiry_minor(self):
        """Ordonnance patient mineur (< 16 ans) → expiration a 1 an (FR59)."""
        today = Date.context_today(self.env['optical.prescription'])
        rx = self.env['optical.prescription'].create({
            'patient_id': self.patient_minor.id,
            'prescriber_id': self.prescriber.id,
            'date': today,
        })
        self.assertEqual(rx.date_expiry, today + relativedelta(years=1))

    def test_expiry_no_birthdate(self):
        """Patient sans date de naissance → defaut 3 ans (AC #5)."""
        today = Date.context_today(self.env['optical.prescription'])
        rx = self.env['optical.prescription'].create({
            'patient_id': self.patient_no_birthdate.id,
            'prescriber_id': self.prescriber.id,
            'date': today,
        })
        self.assertEqual(rx.date_expiry, today + relativedelta(years=3))

    def test_expiry_minor_exact_16(self):
        """Patient 16 ans pile = adulte (3 ans). Patient 16 ans - 1 jour = mineur (1 an)."""
        today = Date.context_today(self.env['optical.prescription'])
        # Patient exactement 16 ans → adulte
        patient_16 = self.env['res.partner'].create({
            'name': 'Patient 16 ans pile',
            'is_patient': True,
            'birthdate': today - relativedelta(years=16),
        })
        rx = self.env['optical.prescription'].create({
            'patient_id': patient_16.id,
            'prescriber_id': self.prescriber.id,
            'date': today,
        })
        self.assertEqual(rx.date_expiry, today + relativedelta(years=3))

        # Patient 16 ans - 1 jour → mineur
        patient_almost_16 = self.env['res.partner'].create({
            'name': 'Patient presque 16 ans',
            'is_patient': True,
            'birthdate': today - relativedelta(years=16) + relativedelta(days=1),
        })
        rx2 = self.env['optical.prescription'].create({
            'patient_id': patient_almost_16.id,
            'prescriber_id': self.prescriber.id,
            'date': today,
        })
        self.assertEqual(rx2.date_expiry, today + relativedelta(years=1))

    def test_expiry_recalculated_on_patient_change(self):
        """Changer le patient recalcule la date d'expiration (AC #6)."""
        today = Date.context_today(self.env['optical.prescription'])
        rx = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'date': today,
        })
        self.assertEqual(rx.date_expiry, today + relativedelta(years=3))
        # Changer vers patient mineur → recalcul a 1 an
        rx.patient_id = self.patient_minor
        self.assertEqual(rx.date_expiry, today + relativedelta(years=1))

    def test_expiry_recalculated_on_birthdate_change(self):
        """Modifier la date de naissance du patient recalcule l'expiration (AC #6)."""
        today = Date.context_today(self.env['optical.prescription'])
        # Patient adulte → 3 ans
        patient = self.env['res.partner'].create({
            'name': 'Patient Birthdate Test',
            'is_patient': True,
            'birthdate': today - relativedelta(years=30),
        })
        rx = self.env['optical.prescription'].create({
            'patient_id': patient.id,
            'prescriber_id': self.prescriber.id,
            'date': today,
        })
        self.assertEqual(rx.date_expiry, today + relativedelta(years=3))
        # Modifier birthdate pour en faire un mineur → recalcul a 1 an
        patient.birthdate = today - relativedelta(years=10)
        self.assertEqual(rx.date_expiry, today + relativedelta(years=1))

    # --- Tests cron expiration (AC #3, #7) ---

    def test_cron_expires_confirmed(self):
        """Cron expire les ordonnances confirmées avec date_expiry depassee (FR12)."""
        today = Date.context_today(self.env['optical.prescription'])
        rx = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'date': today - relativedelta(years=4),
        })
        rx.action_confirm()
        self.assertEqual(rx.state, 'confirmed')
        self.assertTrue(rx.date_expiry < today)
        self.env['optical.prescription']._cron_expire_prescriptions()
        self.assertEqual(rx.state, 'expired')

    def test_cron_does_not_expire_drafts(self):
        """Cron n'expire PAS les ordonnances en draft (AC #7)."""
        today = Date.context_today(self.env['optical.prescription'])
        rx = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'date': today - relativedelta(years=4),
        })
        self.assertEqual(rx.state, 'draft')
        self.assertTrue(rx.date_expiry < today)
        self.env['optical.prescription']._cron_expire_prescriptions()
        self.assertEqual(rx.state, 'draft')

    def test_cron_does_not_expire_future(self):
        """Cron n'expire PAS les ordonnances dont la date_expiry est dans le futur."""
        today = Date.context_today(self.env['optical.prescription'])
        rx = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'date': today,
        })
        rx.action_confirm()
        self.assertTrue(rx.date_expiry > today)
        self.env['optical.prescription']._cron_expire_prescriptions()
        self.assertEqual(rx.state, 'confirmed')

    def test_cron_does_not_expire_today_boundary(self):
        """Ordonnance dont date_expiry == today → NON expiree (dernier jour de validite)."""
        today = Date.context_today(self.env['optical.prescription'])
        # Creer une ordonnance dont l'expiration tombe exactement aujourd'hui
        # date = today - 3 ans → date_expiry = today (pour un adulte)
        rx = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'date': today - relativedelta(years=3),
        })
        rx.action_confirm()
        self.assertEqual(rx.date_expiry, today)
        self.env['optical.prescription']._cron_expire_prescriptions()
        # Le cron utilise date_expiry < today, donc today pile n'est PAS expire
        self.assertEqual(rx.state, 'confirmed')

    def test_cron_batch_volume(self):
        """Cron expire 5 confirmées depassées, laisse 3 confirmées futures intactes."""
        today = Date.context_today(self.env['optical.prescription'])
        Rx = self.env['optical.prescription']
        expired_rxs = Rx
        future_rxs = Rx
        for _i in range(5):
            rx = Rx.create({
                'patient_id': self.patient.id,
                'prescriber_id': self.prescriber.id,
                'date': today - relativedelta(years=4),
            })
            rx.action_confirm()
            expired_rxs |= rx
        for _i in range(3):
            rx = Rx.create({
                'patient_id': self.patient.id,
                'prescriber_id': self.prescriber.id,
                'date': today,
            })
            rx.action_confirm()
            future_rxs |= rx
        Rx._cron_expire_prescriptions()
        self.assertTrue(all(r.state == 'expired' for r in expired_rxs))
        self.assertTrue(all(r.state == 'confirmed' for r in future_rxs))

    # --- Tests validation mesures (AC #4) ---

    def test_validation_sphere_out_of_range(self):
        """Sphere > 20 → ValidationError (FR60)."""
        with self.assertRaises(ValidationError):
            self.env['optical.prescription'].create({
                'patient_id': self.patient.id,
                'prescriber_id': self.prescriber.id,
                'od_sphere': 25.0,
            })

    def test_validation_sphere_valid(self):
        """Sphere = -20.0 (limite exacte) → pas d'erreur."""
        rx = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'od_sphere': -20.0,
        })
        self.assertAlmostEqual(rx.od_sphere, -20.0)

    def test_validation_sphere_boundary(self):
        """Sphere = 20.0 pile → OK. Sphere = 20.01 → ValidationError (FR60)."""
        rx = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'od_sphere': 20.0,
        })
        self.assertAlmostEqual(rx.od_sphere, 20.0)
        with self.assertRaises(ValidationError):
            self.env['optical.prescription'].create({
                'patient_id': self.patient.id,
                'prescriber_id': self.prescriber.id,
                'od_sphere': 20.01,
            })

    def test_validation_cylinder_positive(self):
        """Cylindre positif → ValidationError (FR60)."""
        with self.assertRaises(ValidationError):
            self.env['optical.prescription'].create({
                'patient_id': self.patient.id,
                'prescriber_id': self.prescriber.id,
                'od_cylinder': 1.0,
            })

    def test_validation_cylinder_too_negative(self):
        """Cylindre < -8 → ValidationError (FR60)."""
        with self.assertRaises(ValidationError):
            self.env['optical.prescription'].create({
                'patient_id': self.patient.id,
                'prescriber_id': self.prescriber.id,
                'og_cylinder': -9.0,
            })

    def test_validation_cylinder_zero(self):
        """Cylindre = 0.0 → pas d'erreur (champ non renseigne)."""
        rx = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'od_cylinder': 0.0,
        })
        self.assertAlmostEqual(rx.od_cylinder, 0.0)

    def test_validation_axis_out_of_range(self):
        """Axe > 180 → ValidationError (FR60)."""
        with self.assertRaises(ValidationError):
            self.env['optical.prescription'].create({
                'patient_id': self.patient.id,
                'prescriber_id': self.prescriber.id,
                'od_axis': 200,
            })

    def test_validation_axis_boundary(self):
        """Axe = 180 (limite exacte) → pas d'erreur."""
        rx = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'od_axis': 180,
        })
        self.assertEqual(rx.od_axis, 180)

    def test_validation_addition_negative(self):
        """Addition negative → ValidationError (FR60)."""
        with self.assertRaises(ValidationError):
            self.env['optical.prescription'].create({
                'patient_id': self.patient.id,
                'prescriber_id': self.prescriber.id,
                'og_addition': -1.0,
            })

    def test_validation_og_sphere_out_of_range(self):
        """OG Sphere hors plage → ValidationError (FR60)."""
        with self.assertRaises(ValidationError):
            self.env['optical.prescription'].create({
                'patient_id': self.patient.id,
                'prescriber_id': self.prescriber.id,
                'og_sphere': -21.0,
            })

    def test_validation_og_axis_out_of_range(self):
        """OG Axe hors plage → ValidationError (FR60)."""
        with self.assertRaises(ValidationError):
            self.env['optical.prescription'].create({
                'patient_id': self.patient.id,
                'prescriber_id': self.prescriber.id,
                'og_axis': 181,
            })

    def test_validation_addition_out_of_range(self):
        """Addition > 4 → ValidationError (FR60)."""
        with self.assertRaises(ValidationError):
            self.env['optical.prescription'].create({
                'patient_id': self.patient.id,
                'prescriber_id': self.prescriber.id,
                'od_addition': 5.0,
            })


@tagged('post_install', '-at_install')
class TestPrescriptionDiopterStep(OpticalTestCommon):
    """Tests Story 3.5 : Validation step 0,25 et helper format_diopter."""

    # --- Tests validation step 0,25 (AC #3) ---

    def test_step_validation_sphere(self):
        """Sphere = 1.30 (non multiple de 0,25) → ValidationError."""
        with self.assertRaises(ValidationError):
            self.env['optical.prescription'].create({
                'patient_id': self.patient.id,
                'prescriber_id': self.prescriber.id,
                'od_sphere': 1.30,
            })

    def test_step_validation_sphere_valid(self):
        """Sphere = 1.25 (multiple de 0,25) → OK."""
        rx = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'od_sphere': 1.25,
        })
        self.assertAlmostEqual(rx.od_sphere, 1.25)

    def test_step_validation_cylinder(self):
        """Cylindre = -1.30 (non multiple de 0,25) → ValidationError."""
        with self.assertRaises(ValidationError):
            self.env['optical.prescription'].create({
                'patient_id': self.patient.id,
                'prescriber_id': self.prescriber.id,
                'od_cylinder': -1.30,
            })

    def test_step_validation_cylinder_valid(self):
        """Cylindre = -1.25 (multiple de 0,25) → OK."""
        rx = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'od_cylinder': -1.25,
        })
        self.assertAlmostEqual(rx.od_cylinder, -1.25)

    def test_step_validation_addition(self):
        """Addition = 1.10 (non multiple de 0,25) → ValidationError."""
        with self.assertRaises(ValidationError):
            self.env['optical.prescription'].create({
                'patient_id': self.patient.id,
                'prescriber_id': self.prescriber.id,
                'od_addition': 1.10,
            })

    def test_step_validation_addition_valid(self):
        """Addition = 1.00 (multiple de 0,25) → OK."""
        rx = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'od_addition': 1.00,
        })
        self.assertAlmostEqual(rx.od_addition, 1.00)

    def test_step_validation_prism_exempt(self):
        """Prisme = 1.30 → PAS d'erreur (prisme non soumis au step)."""
        rx = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'od_prism': 1.30,
        })
        self.assertAlmostEqual(rx.od_prism, 1.30)

    def test_step_validation_zero(self):
        """Sphere = 0.0 → OK (zero non valide car falsy)."""
        rx = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'od_sphere': 0.0,
        })
        self.assertAlmostEqual(rx.od_sphere, 0.0)

    # --- Tests helper format_diopter (AC #5) ---

    def test_format_diopter_positive(self):
        """format_diopter(1.25) → '+1,25'."""
        rx = self.prescription
        self.assertEqual(rx.format_diopter(1.25), "+1,25")

    def test_format_diopter_negative(self):
        """format_diopter(-0.5) → '-0,50'."""
        rx = self.prescription
        self.assertEqual(rx.format_diopter(-0.5), "-0,50")

    def test_format_diopter_zero(self):
        """format_diopter(0) → '0,00'."""
        rx = self.prescription
        self.assertEqual(rx.format_diopter(0), "0,00")

    def test_format_diopter_one_decimal(self):
        """format_diopter(32.5, decimals=1) → '+32,5'."""
        rx = self.prescription
        self.assertEqual(rx.format_diopter(32.5, decimals=1), "+32,5")

    def test_format_diopter_false(self):
        """format_diopter(False) → '' (champ vide, pas de valeur)."""
        rx = self.prescription
        self.assertEqual(rx.format_diopter(False), "")

    def test_format_diopter_none(self):
        """format_diopter(None) → '' (champ vide)."""
        rx = self.prescription
        self.assertEqual(rx.format_diopter(None), "")

    # --- Test OG step validation (couverture branche OG) ---

    def test_step_validation_og_sphere(self):
        """OG Sphere = 1.30 (non multiple de 0,25) → ValidationError."""
        with self.assertRaises(ValidationError):
            self.env['optical.prescription'].create({
                'patient_id': self.patient.id,
                'prescriber_id': self.prescriber.id,
                'og_sphere': 1.30,
            })
