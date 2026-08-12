# -*- coding: utf-8 -*-
"""Tests Story 19-2 — Référentiel optical.lens.index.

Ne rejoint pas TestOpticalAttributes.ATTRIBUTE_MODELS car le modèle diverge
volontairement (pas de color, _order='value', contrainte sur value).
"""
from psycopg2 import IntegrityError

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestOpticalLensIndex(OpticalTestCommon):
    """Tests dédiés au modèle optical.lens.index (Story 19-2)."""

    def test_index_value_uniqueness(self):
        """AC-1.2 : contrainte SQL unique sur value (peu importe le libellé)."""
        Model = self.env['optical.lens.index']
        Model.create({'name': '1.60', 'value': 1.60})
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            Model.create({'name': '1.60 – Aminci', 'value': 1.60})

    def test_index_ordering_by_value(self):
        """AC-1.3 : _order='value' croissant."""
        Model = self.env['optical.lens.index']
        Model.create({'name': '1.74', 'value': 1.74})
        Model.create({'name': '1.50', 'value': 1.50})
        Model.create({'name': '1.60', 'value': 1.60})
        Model.create({'name': '1.56', 'value': 1.56})
        records = Model.search([])
        values = records.mapped('value')
        self.assertEqual(
            values, sorted(values),
            "Les indices doivent être triés par value croissante",
        )

    def test_index_acl_non_optical_user_denied(self):
        """AC-3.3 : utilisateur sans groupe optique → AccessError en lecture."""
        record = self.env['optical.lens.index'].create({
            'name': '1.60', 'value': 1.60,
        })
        with self.assertRaises(AccessError):
            record.with_user(self.user_sans_groupe).read(['name', 'value'])
