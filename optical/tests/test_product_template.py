# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestProductTemplate(OpticalTestCommon):
    """Tests Story 4.2 : Extension product.template et classification optique."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Attributs de test (Story 4.1)
        cls.treatment_ar = cls.env['optical.lens.treatment'].create({
            'name': 'Anti-reflets Test',
        })
        cls.treatment_uv = cls.env['optical.lens.treatment'].create({
            'name': 'Anti-UV Test',
        })
        cls.tint_grey = cls.env['optical.lens.tint'].create({
            'name': 'Gris Test',
        })
        cls.material_titan = cls.env['optical.frame.material'].create({
            'name': 'Titane Test',
        })
        cls.color_noir = cls.env['optical.frame.color'].create({
            'name': 'Noir Test',
        })
        cls.color_or = cls.env['optical.frame.color'].create({
            'name': 'Or Test',
        })
        cls.usage_vue = cls.env['optical.frame.usage'].create({
            'name': 'Vue Test',
        })
        cls.usage_sport = cls.env['optical.frame.usage'].create({
            'name': 'Sport Test',
        })

    def test_optical_type_classification(self):
        """AC #1 : Le vendeur peut classifier un produit par type optique."""
        ProductTemplate = self.env['product.template']
        for optical_type, label in [
            ('frame', 'Monture'),
            ('lens', 'Verre'),
            ('contact_lens', 'Lentille'),
            ('accessory', 'Accessoire'),
            ('service', 'Service'),
        ]:
            with self.subTest(optical_type=optical_type):
                product = ProductTemplate.create({
                    'name': f'Produit Test {label}',
                    'optical_type': optical_type,
                })
                self.assertEqual(product.optical_type, optical_type)

    def test_frame_attributes(self):
        """AC #2 : Le vendeur peut renseigner les attributs specifiques d'une monture."""
        from odoo import Command
        frame = self.env['product.template'].create({
            'name': 'Monture RAYBAN Aviator Test',
            'optical_type': 'frame',
            'frame_shape': 'aviator',
            'frame_gender': 'mixed',
            'frame_rim_type': 'full_rim',
            'lens_width': 54,
            'bridge_width': 17,
            'temple_length': 140,
            'frame_material_ids': [Command.set([self.material_titan.id])],
            'frame_color_ids': [Command.set([self.color_noir.id, self.color_or.id])],
            'frame_usage_ids': [Command.set([self.usage_vue.id, self.usage_sport.id])],
        })
        self.assertEqual(frame.optical_type, 'frame')
        self.assertEqual(frame.frame_shape, 'aviator')
        self.assertEqual(frame.frame_gender, 'mixed')
        self.assertEqual(frame.frame_rim_type, 'full_rim')
        self.assertEqual(frame.lens_width, 54)
        self.assertEqual(frame.bridge_width, 17)
        self.assertEqual(frame.temple_length, 140)
        self.assertIn(self.material_titan, frame.frame_material_ids)
        self.assertEqual(len(frame.frame_color_ids), 2)
        self.assertEqual(len(frame.frame_usage_ids), 2)

    def test_lens_attributes(self):
        """AC #3 : Le vendeur peut renseigner les attributs specifiques d'un verre."""
        from odoo import Command
        index_167 = self.env['optical.lens.index'].create({
            'name': '1.67', 'value': 1.67,
        })
        lens = self.env['product.template'].create({
            'name': 'Verre Progressif Essilor Test',
            'optical_type': 'lens',
            'lens_design': 'progressive',
            'lens_surface': 'freeform',
            'lens_material': 'organic',
            'lens_index_id': index_167.id,
            'lens_diameter': 75.0,
            'lens_treatment_ids': [Command.set([
                self.treatment_ar.id, self.treatment_uv.id,
            ])],
            'lens_tint_ids': [Command.set([self.tint_grey.id])],
        })
        self.assertEqual(lens.optical_type, 'lens')
        self.assertEqual(lens.lens_design, 'progressive')
        self.assertEqual(lens.lens_surface, 'freeform')
        self.assertEqual(lens.lens_material, 'organic')
        self.assertEqual(lens.lens_index_id.value, 1.67)
        self.assertAlmostEqual(lens.lens_diameter, 75.0, places=1)
        self.assertEqual(len(lens.lens_treatment_ids), 2)
        self.assertIn(self.tint_grey, lens.lens_tint_ids)

    def test_filter_by_optical_type(self):
        """AC #4 : Le vendeur peut filtrer le catalogue par type optique."""
        ProductTemplate = self.env['product.template']
        frame = ProductTemplate.create({
            'name': 'Filtre Monture Test',
            'optical_type': 'frame',
        })
        lens = ProductTemplate.create({
            'name': 'Filtre Verre Test',
            'optical_type': 'lens',
        })
        # Filtre montures uniquement
        frames = ProductTemplate.search([('optical_type', '=', 'frame')])
        self.assertIn(frame, frames)
        self.assertNotIn(lens, frames)
        # Filtre verres uniquement
        lenses = ProductTemplate.search([('optical_type', '=', 'lens')])
        self.assertIn(lens, lenses)
        self.assertNotIn(frame, lenses)

    def test_product_brand_dependency(self):
        """AC #5 : Le champ product_brand_id est disponible via OCA product_brand."""
        field = self.env['product.template']._fields.get('product_brand_id')
        self.assertIsNotNone(field, "Le champ product_brand_id doit exister sur product.template")

    def test_contact_lens_same_as_lens(self):
        """AC #6 : Les lentilles de contact ont les memes attributs verre."""
        from odoo import Command
        index_159 = self.env['optical.lens.index'].create({
            'name': '1.59', 'value': 1.59,
        })
        contact_lens = self.env['product.template'].create({
            'name': 'Lentille Contact Test',
            'optical_type': 'contact_lens',
            'lens_design': 'single_vision',
            'lens_material': 'polycarbonate',
            'lens_index_id': index_159.id,
            'lens_treatment_ids': [Command.set([self.treatment_ar.id])],
            'lens_tint_ids': [Command.set([self.tint_grey.id])],
        })
        self.assertEqual(contact_lens.optical_type, 'contact_lens')
        self.assertEqual(contact_lens.lens_design, 'single_vision')
        self.assertEqual(contact_lens.lens_material, 'polycarbonate')
        self.assertEqual(len(contact_lens.lens_treatment_ids), 1)
        self.assertEqual(len(contact_lens.lens_tint_ids), 1)

    def test_accessory_service_no_optical_attrs(self):
        """AC #7 : Accessoire et service fonctionnent sans attributs optiques."""
        for optical_type in ('accessory', 'service'):
            with self.subTest(optical_type=optical_type):
                product = self.env['product.template'].create({
                    'name': f'Produit {optical_type} Test',
                    'optical_type': optical_type,
                })
                self.assertEqual(product.optical_type, optical_type)
                # Les champs optiques specifiques restent vides
                self.assertFalse(product.frame_shape)
                self.assertFalse(product.lens_design)
                self.assertFalse(product.frame_material_ids)
                self.assertFalse(product.lens_treatment_ids)

    def test_product_without_optical_type(self):
        """NFR15 : Un produit sans type optique fonctionne normalement."""
        product = self.env['product.template'].create({
            'name': 'Produit Standard Sans Optique',
            'list_price': 10000.0,
        })
        self.assertFalse(product.optical_type)
        # Le produit fonctionne normalement
        self.assertEqual(product.name, 'Produit Standard Sans Optique')
        self.assertEqual(product.list_price, 10000.0)
        # N'apparait pas dans le filtre catalogue optique
        optical_products = self.env['product.template'].search([
            ('optical_type', '!=', False),
        ])
        self.assertNotIn(product, optical_products)

    # ------------------------------------------------------------------
    # Story 19-4 — Tests dédiés `lens_thickness_id` + `product_brand_id`
    # sur `product.template` (page Verre)
    # ------------------------------------------------------------------

    def test_lens_thickness_field_definition(self):
        """Story 19-4 AC-1.1 : le champ lens_thickness_id est Many2one → optical.lens.thickness, optionnel."""
        field = self.env['product.template']._fields.get('lens_thickness_id')
        self.assertIsNotNone(field, "Le champ lens_thickness_id doit exister sur product.template")
        self.assertEqual(field.type, 'many2one')
        self.assertEqual(field.comodel_name, 'optical.lens.thickness')
        self.assertFalse(field.required, "lens_thickness_id doit être required=False (cadrage Q1/Q24)")

    def test_lens_creates_with_thickness_and_brand(self):
        """Story 19-4 AC-3.1 : un verre porte lens_index_id + lens_thickness_id + product_brand_id en un seul create."""
        aminci = self.env['optical.lens.thickness'].create({'name': 'Aminci Test S19-4'})
        index_160 = self.env['optical.lens.index'].create({'name': '1.60 Test S19-4', 'value': 1.60})
        brand_essilor = self.env['product.brand'].create({'name': 'Essilor Test S19-4'})
        lens = self.env['product.template'].create({
            'name': 'Verre Test S19-4 Complet',
            'optical_type': 'lens',
            'lens_design': 'single_vision',
            'lens_material': 'organic',
            'lens_index_id': index_160.id,
            'lens_thickness_id': aminci.id,
            'product_brand_id': brand_essilor.id,
        })
        self.assertEqual(lens.optical_type, 'lens')
        self.assertEqual(lens.lens_index_id.value, 1.60)
        self.assertEqual(lens.lens_thickness_id.name, 'Aminci Test S19-4')
        self.assertEqual(lens.product_brand_id.name, 'Essilor Test S19-4')

    def test_frame_can_hold_brand_lens_thickness_stays_false(self):
        """Story 19-4 AC-3.2 : une monture peut porter product_brand_id ; lens_thickness_id reste False par défaut."""
        brand_rayban = self.env['product.brand'].create({'name': 'Ray-Ban Test S19-4'})
        frame = self.env['product.template'].create({
            'name': 'Monture Test S19-4',
            'optical_type': 'frame',
            'product_brand_id': brand_rayban.id,
        })
        self.assertEqual(frame.optical_type, 'frame')
        self.assertEqual(frame.product_brand_id.name, 'Ray-Ban Test S19-4')
        # AC-3.2 : le champ verre reste False par défaut sur une monture (aucune contrainte, juste comportement métier)
        self.assertFalse(frame.lens_thickness_id, "lens_thickness_id doit être False par défaut sur une monture")

    def test_lens_thickness_can_be_modified(self):
        """Story 19-4 AC-1.3 (write cycle) : modifier lens_thickness_id vers une autre épaisseur persiste la nouvelle valeur."""
        aminci = self.env['optical.lens.thickness'].create({'name': 'Aminci Test S19-4 write'})
        ultra_aminci = self.env['optical.lens.thickness'].create({'name': 'Ultra-aminci Test S19-4 write'})
        lens = self.env['product.template'].create({
            'name': 'Verre Write-cycle Test S19-4',
            'optical_type': 'lens',
            'lens_thickness_id': aminci.id,
        })
        self.assertEqual(lens.lens_thickness_id, aminci)
        lens.lens_thickness_id = ultra_aminci
        lens.invalidate_recordset(['lens_thickness_id'])
        self.assertEqual(lens.lens_thickness_id, ultra_aminci)
        self.assertEqual(lens.lens_thickness_id.name, 'Ultra-aminci Test S19-4 write')

    def test_frame_can_write_lens_thickness_no_constraint(self):
        """Story 19-4 AC-1.4 : forcer lens_thickness_id sur une monture via API réussit (aucune contrainte modèle)."""
        aminci = self.env['optical.lens.thickness'].create({'name': 'Aminci Test S19-4 no-constraint'})
        frame = self.env['product.template'].create({
            'name': 'Monture Test S19-4 no-constraint',
            'optical_type': 'frame',
        })
        # AC-1.4 : aucune contrainte @api.constrains ne bloque cette écriture — le contrôle vit uniquement en vue.
        frame.lens_thickness_id = aminci
        self.assertEqual(frame.lens_thickness_id, aminci)

    def test_contact_lens_can_hold_thickness_and_brand(self):
        """Story 19-4 AC-2.3 : une lentille de contact peut porter lens_thickness_id + product_brand_id (page Verre reste visible)."""
        aminci = self.env['optical.lens.thickness'].create({'name': 'Aminci Test S19-4 contact'})
        brand_alcon = self.env['product.brand'].create({'name': 'Alcon Test S19-4'})
        contact_lens = self.env['product.template'].create({
            'name': 'Lentille Test S19-4 thickness+brand',
            'optical_type': 'contact_lens',
            'lens_thickness_id': aminci.id,
            'product_brand_id': brand_alcon.id,
        })
        self.assertEqual(contact_lens.optical_type, 'contact_lens')
        self.assertEqual(contact_lens.lens_thickness_id.name, 'Aminci Test S19-4 contact')
        self.assertEqual(contact_lens.product_brand_id.name, 'Alcon Test S19-4')
