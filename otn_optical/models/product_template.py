# Copyright 2017 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).
from random import randint
from odoo import fields, models, api


class ProductTemplate(models.Model):
    _inherit = "product.template"

    lens_treatment_ids = fields.Many2many('product.lens.treatment', string='Traitements')
    optical_product_type = fields.Selection([
        ("lenses", "Verres"),
        ("frames", "Montures"),
        ("contact_lenses", "Lentilles"),
        ("others", "Autres"),
    ], string="Type de produit optique", default="others", required=True)

    lens_od_sphere = fields.Char(string="OD Sphère")
    lens_og_sphere = fields.Char(string="OG Sphère")
    lens_od_cylinder = fields.Char(string="OD Cylindre")
    lens_og_cylinder = fields.Char(string="OG Cylindre")
    lens_addition = fields.Char(string="Addition")

    lens_type_ids = fields.Many2many('product.lens.type', string='Type de verre')
    lens_surface = fields.Selection([
        ('spherical', 'Sphérique'),
        ('aspherical', 'Asphérique')
    ], string='Surface')
    lens_material = fields.Selection([
        ('organic', 'Organique'),
        ('polycarbonate', 'Polycarbonate'),
        ('mineral', 'Minérale')
    ], string='Matière')
    lens_diameter = fields.Float('Diamètre')
    lens_index = fields.Float('Indice')

    # :::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::
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
    ], string='Forme de la monture')
    frame_gender = fields.Selection([
        ('man', 'Homme'),
        ('woman', 'Femme'),
        ('mixed', 'Mixte'),
        ('boy', 'Garçon'),
        ('girl', 'Fille'),
    ], string='Forme de la monture')
    frame_color_ids = fields.Many2many('product.frame.color', string='Couleur de la monture')
    frame_material_ids = fields.Many2many('product.frame.material', string='Matière de la monture')
    frame_usage_ids = fields.Many2many('product.frame.usage', string="Type d'usage")
    frame_rim_type = fields.Selection([
        ('rimless', 'Non cerclée'),
        ('semi_rimless', 'Semi-cerclée'),
        ('full_rim', 'Cerclée'),
    ], string='Type de cercle')
    lens_width = fields.Integer(string='Largeur des verres (mm)')
    bridge_width = fields.Integer(string='Largeur du pont (mm)')
    temple_length = fields.Integer(string='Longueur des bras (mm)')


class OpticalProductAttributeMixin(models.AbstractModel):
    _name = "optical.product.attribute.mixin"
    _order = 'sequence'
    _description = "Optical product attribute"

    def _get_default_color(self):
        return randint(1, 11)

    name = fields.Char(string='Nom', required=True)
    color = fields.Integer('Couleur', default=_get_default_color)
    sequence = fields.Integer(default=10)

class LensTreatment(models.Model):
    _name = 'product.lens.treatment'
    _inherit = 'optical.product.attribute.mixin'
    _description = 'Traitement de verre'

    def _get_default_color(self):
        return 1


class LensType(models.Model):
    _name = 'product.lens.type'
    _inherit = 'optical.product.attribute.mixin'
    _description = 'Type de verre'

    def _get_default_color(self):
        return 2

class FrameMaterial(models.Model):
    _name = 'product.frame.material'
    _inherit = 'optical.product.attribute.mixin'
    _description = 'Matière des montures'

    def _get_default_color(self):
        return 3


class FrameUsage(models.Model):
    _name = 'product.frame.usage'
    _inherit = 'optical.product.attribute.mixin'
    _description = 'Usage des montures'

    def _get_default_color(self):
        return 4

class FrameColor(models.Model):
    _name = 'product.frame.color'
    _inherit = 'optical.product.attribute.mixin'
    _description = 'Couleur des montures'

    def _get_default_color(self):
        return 5




