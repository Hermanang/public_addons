# -*- coding: utf-8 -*-
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestResPartner(OpticalTestCommon):
    """Tests de l'extension res.partner (is_patient, is_insurer)."""

    def test_create_patient(self):
        """Création d'un contact avec is_patient=True."""
        partner = self.env['res.partner'].create({
            'name': 'Nouveau Patient',
            'is_patient': True,
        })
        self.assertTrue(partner.is_patient)
        self.assertFalse(partner.is_insurer)

    def test_create_insurer(self):
        """Création d'un contact avec is_insurer=True."""
        partner = self.env['res.partner'].create({
            'name': 'Nouvel Assureur',
            'is_insurer': True,
        })
        self.assertTrue(partner.is_insurer)
        self.assertFalse(partner.is_patient)

    def test_search_patients_only(self):
        """Le domain [('is_patient', '=', True)] retourne uniquement les patients."""
        # Créer un contact non-patient pour s'assurer du filtrage
        self.env['res.partner'].create({
            'name': 'Contact Normal',
        })
        patients = self.env['res.partner'].search([('is_patient', '=', True)])
        for p in patients:
            self.assertTrue(p.is_patient, f"Le partenaire {p.name} ne devrait pas être dans les patients")

    def test_search_insurers_only(self):
        """Le domain [('is_insurer', '=', True)] retourne uniquement les assureurs."""
        self.env['res.partner'].create({
            'name': 'Contact Normal 2',
        })
        insurers = self.env['res.partner'].search([('is_insurer', '=', True)])
        for ins in insurers:
            self.assertTrue(ins.is_insurer, f"Le partenaire {ins.name} ne devrait pas être dans les assureurs")

    def test_create_prescriber(self):
        """Création d'un prescripteur avec enregistrement et spécialité."""
        partner = self.env['res.partner'].create({
            'name': 'Dr. Dupont',
            'is_prescriber': True,
            'prescriber_registration': 'MED-99999',
            'prescriber_specialty': 'ophthalmologist',
        })
        self.assertTrue(partner.is_prescriber)
        self.assertEqual(partner.prescriber_registration, 'MED-99999')
        self.assertEqual(partner.prescriber_specialty, 'ophthalmologist')

    def test_search_prescribers_only(self):
        """Le domain [('is_prescriber', '=', True)] retourne uniquement les prescripteurs."""
        self.env['res.partner'].create({
            'name': 'Contact Normal 3',
        })
        prescribers = self.env['res.partner'].search([('is_prescriber', '=', True)])
        for p in prescribers:
            self.assertTrue(p.is_prescriber, f"Le partenaire {p.name} ne devrait pas être dans les prescripteurs")

    def test_default_values(self):
        """Par défaut, is_patient, is_insurer et is_prescriber sont False."""
        partner = self.env['res.partner'].create({
            'name': 'Contact Lambda',
        })
        self.assertFalse(partner.is_patient)
        self.assertFalse(partner.is_insurer)
        self.assertFalse(partner.is_prescriber)


@tagged('post_install', '-at_install')
class TestPatientDossier(OpticalTestCommon):
    """Tests Story 3.4 : Dossier patient et historique ordonnances."""

    def test_prescription_count_smart_button(self):
        """AC #1 : Smart button ordonnances affiche le bon compteur et action correcte."""
        # self.patient a 2 ordonnances (prescription + prescription_confirmed) via common.py
        self.patient.invalidate_recordset(['prescription_count'])
        self.assertEqual(self.patient.prescription_count, 2)

        # Verifier l'action retournee
        action = self.patient.action_view_prescriptions()
        self.assertEqual(action['res_model'], 'optical.prescription')
        self.assertEqual(action['view_mode'], 'list,form')
        self.assertEqual(action['domain'], [('patient_id', '=', self.patient.id)])

    def test_policy_count_smart_button(self):
        """AC #1, #5 : Smart button polices affiche le bon compteur et action correcte."""
        # self.patient a 2 polices via common.py (policy + policy_full)
        self.patient.invalidate_recordset(['policy_count'])
        self.assertEqual(self.patient.policy_count, 2)

        action = self.patient.action_view_policies()
        self.assertEqual(action['res_model'], 'optical.policy')
        self.assertEqual(action['view_mode'], 'list,form')
        self.assertEqual(action['domain'], [('patient_id', '=', self.patient.id)])

    def test_prescription_history_all_states(self):
        """AC #2, #4 : L'historique affiche toutes les ordonnances avec leurs etats."""
        # Creer une ordonnance expiree
        expired_rx = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'od_sphere': 1.00,
            'og_sphere': 1.50,

        })
        expired_rx.action_confirm()
        expired_rx.write({'state': 'expired'})

        self.patient.invalidate_recordset(['prescription_ids', 'prescription_count'])
        # 3 ordonnances : prescription (draft), prescription_confirmed (confirmed), expired_rx (expired)
        self.assertEqual(self.patient.prescription_count, 3)
        states = self.patient.prescription_ids.mapped('state')
        self.assertIn('draft', states)
        self.assertIn('confirmed', states)
        self.assertIn('expired', states)

    def test_patient_no_prescription(self):
        """AC #3 : Patient sans ordonnance → prescription_count == 0."""
        patient_empty = self.env['res.partner'].create({
            'name': 'Patient Vide',
            'is_patient': True,
        })
        self.assertEqual(patient_empty.prescription_count, 0)
        self.assertFalse(patient_empty.prescription_ids)

    def test_non_patient_counts_zero(self):
        """AC #7 : Contact non-patient → tous les compteurs a 0."""
        contact = self.env['res.partner'].create({
            'name': 'Contact Standard',
        })
        self.assertEqual(contact.prescription_count, 0)
        self.assertEqual(contact.policy_count, 0)
