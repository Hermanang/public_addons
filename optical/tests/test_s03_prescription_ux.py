# -*- coding: utf-8 -*-
import ast

from odoo.fields import Date
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestPrescriptionUX(OpticalTestCommon):
    """Tests Story 3.6 : Enrichissement ordonnance (CC-2026-03-07-PRESCRIPTION-UX)."""

    # --- Tests champs metier (FR71) ---

    def test_vision_type_field(self):
        """vision_type peut etre renseigne et lu."""
        self.prescription.vision_type = 'progressive'
        self.assertEqual(self.prescription.vision_type, 'progressive')

    def test_measure_type_field(self):
        """measure_type peut etre renseigne et lu."""
        self.prescription.measure_type = 'glasses'
        self.assertEqual(self.prescription.measure_type, 'glasses')

    def test_measure_date_field(self):
        """measure_date peut etre renseigne et lu."""
        today = Date.context_today(self.prescription)
        self.prescription.measure_date = today
        self.assertEqual(self.prescription.measure_date, today)

    def test_create_with_new_fields(self):
        """Creation d'une ordonnance avec les 3 nouveaux champs."""
        today = Date.context_today(self.env['optical.prescription'])
        rx = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'vision_type': 'far',
            'measure_type': 'contact_lenses',
            'measure_date': today,
            'od_sphere': 1.00,
        })
        self.assertEqual(rx.vision_type, 'far')
        self.assertEqual(rx.measure_type, 'contact_lenses')
        self.assertEqual(rx.measure_date, today)

    def test_new_fields_optional(self):
        """Les 3 champs sont optionnels — creation sans eux fonctionne."""
        rx = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
        })
        self.assertFalse(rx.vision_type)
        self.assertFalse(rx.measure_type)
        self.assertFalse(rx.measure_date)

    # --- Tests related fields sur sale.order ---

    def test_related_fields_on_sale_order(self):
        """Les 3 related fields sont accessibles sur sale.order."""
        today = Date.context_today(self.env['optical.prescription'])
        self.prescription_confirmed.write({
            'vision_type': 'near',
            'measure_type': 'glasses',
            'measure_date': today,
        })
        self.sale_order.prescription_id = self.prescription_confirmed.id
        self.assertEqual(self.sale_order.prescription_vision_type, 'near')
        self.assertEqual(self.sale_order.prescription_measure_type, 'glasses')
        self.assertEqual(self.sale_order.prescription_measure_date, today)

    def test_prism_related_fields_on_sale_order(self):
        """Les related fields prisme sont accessibles sur sale.order."""
        self.prescription_confirmed.write({
            'od_prism': 1.50,
            'od_prism_base': 'up',
            'og_prism': 0.75,
            'og_prism_base': 'in',
        })
        self.sale_order.prescription_id = self.prescription_confirmed.id
        self.assertAlmostEqual(self.sale_order.prescription_od_prism, 1.50)
        self.assertEqual(self.sale_order.prescription_od_prism_base, 'up')
        self.assertAlmostEqual(self.sale_order.prescription_og_prism, 0.75)
        self.assertEqual(self.sale_order.prescription_og_prism_base, 'in')

    # --- Tests accents labels state (NFR18) ---

    def test_state_labels_accents(self):
        """Les labels du state portent les accents corrects (NFR18)."""
        field = self.env['optical.prescription']._fields['state']
        selection = dict(field.selection)
        self.assertEqual(selection['confirmed'], "Confirmé")
        self.assertEqual(selection['expired'], "Expiré")

    def test_state_string_accent(self):
        """Le string du champ state porte l'accent correct (NFR18)."""
        field = self.env['optical.prescription']._fields['state']
        self.assertEqual(field.string, "État")

    # --- Tests vision_type selection values ---

    def test_vision_type_all_values(self):
        """Toutes les valeurs de vision_type sont valides."""
        for value in ('far', 'near', 'intermediate', 'progressive'):
            self.prescription.vision_type = value
            self.assertEqual(self.prescription.vision_type, value)

    def test_measure_type_all_values(self):
        """Toutes les valeurs de measure_type sont valides."""
        for value in ('glasses', 'contact_lenses'):
            self.prescription.measure_type = value
            self.assertEqual(self.prescription.measure_type, value)

    # --- Tests tableau HTML (AC#2, AC#3) ---

    def test_prescription_form_table_html(self):
        """AC#2 — Les mesures ordonnance sont dans un tableau HTML."""
        view = self.env.ref('optical.optical_prescription_view_form')
        self.assertIn('table table-bordered table-sm', view.arch)
        self.assertIn('<th>Sphère</th>', view.arch)
        self.assertIn('<strong>OD</strong>', view.arch)
        self.assertIn('<strong>OG</strong>', view.arch)

    def test_sale_order_form_table_html(self):
        """AC#3 — Les mesures related sale.order sont dans un tableau HTML."""
        view = self.env.ref('optical.view_order_form_optical')
        self.assertIn('table table-bordered table-sm', view.arch)
        self.assertIn('prescription_od_sphere', view.arch)
        self.assertIn('prescription_og_sphere', view.arch)

    # --- Tests default_is_company (AC#5) ---

    def test_default_is_company_patient(self):
        """AC#5 — Patient : default_is_company=False."""
        action = self.env.ref('optical.optical_patient_action')
        ctx = ast.literal_eval(action.context)
        self.assertFalse(ctx.get('default_is_company'))

    def test_default_is_company_insurance(self):
        """AC#5 — Assurance : default_is_company=True."""
        action = self.env.ref('optical.optical_insurance_action')
        ctx = ast.literal_eval(action.context)
        self.assertTrue(ctx.get('default_is_company'))

    def test_default_is_company_ipm(self):
        """AC#5 — IPM : default_is_company=True."""
        action = self.env.ref('optical.optical_ipm_action')
        ctx = ast.literal_eval(action.context)
        self.assertTrue(ctx.get('default_is_company'))
