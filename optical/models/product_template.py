# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # === Classification optique ===
    optical_type = fields.Selection([
        ('frame', 'Monture'),
        ('lens', 'Verre'),
        ('contact_lens', 'Lentille de contact'),
        ('accessory', 'Accessoire'),
        ('service', 'Service'),
    ], string="Type optique", index=True)

    # === Attributs monture (visible si optical_type == 'frame') ===
    frame_shape = fields.Selection([
        ('rectangular', 'Rectangulaire'),
        ('oval', 'Ovale'),
        ('square', 'Carré'),
        ('browline', 'Browline'),
        ('aviator', 'Aviateur'),
        ('round', 'Rond'),
        ('butterfly', 'Papillon'),
        ('geometric', 'Géométrique'),
        ('heart', 'Cœur'),
    ], string="Forme")
    frame_gender = fields.Selection([
        ('man', 'Homme'),
        ('woman', 'Femme'),
        ('mixed', 'Mixte'),
        ('boy', 'Garçon'),
        ('girl', 'Fille'),
    ], string="Genre")
    frame_rim_type = fields.Selection([
        ('full_rim', 'Cerclée'),
        ('semi_rimless', 'Semi-cerclée'),
        ('rimless', 'Non cerclée'),
    ], string="Type de cerclage")
    lens_width = fields.Integer(string="Largeur verres (mm)")
    bridge_width = fields.Integer(string="Largeur pont (mm)")
    temple_length = fields.Integer(string="Longueur branches (mm)")
    # product_brand_id : fourni par OCA product_brand — NE PAS RECREER
    frame_material_ids = fields.Many2many(
        'optical.frame.material', string="Matériaux")
    frame_color_ids = fields.Many2many(
        'optical.frame.color', string="Couleurs")
    frame_usage_ids = fields.Many2many(
        'optical.frame.usage', string="Usages")

    # === Attributs verre (visible si optical_type in ('lens', 'contact_lens')) ===
    lens_design = fields.Selection([
        ('single_vision', 'Unifocal'),
        ('progressive', 'Progressif'),
        ('bifocal', 'Bifocal'),
        ('degressive', 'Dégressif'),
        ('mid_distance', 'Mi-distance'),
    ], string="Design")
    lens_surface = fields.Selection([
        ('spherical', 'Sphérique'),
        ('aspherical', 'Asphérique'),
        ('double_aspherical', 'Double asphérique'),
        ('freeform', 'Freeform'),
    ], string="Surface")
    lens_material = fields.Selection([
        ('organic', 'Organique'),
        ('polycarbonate', 'Polycarbonate'),
        ('mineral', 'Minérale'),
        ('trivex', 'Trivex'),
    ], string="Matériau")
    lens_index = fields.Float(string="Indice de réfraction")
    lens_diameter = fields.Float(string="Diamètre (mm)")
    lens_treatment_ids = fields.Many2many(
        'optical.lens.treatment', string="Traitements")
    lens_tint_ids = fields.Many2many(
        'optical.lens.tint', string="Teintes")
