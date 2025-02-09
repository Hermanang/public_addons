# Copyright 2017 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).
from email.policy import default

from odoo import fields, models


class Product(models.Model):
    _inherit = "product.product"

    od_sphere = fields.Char(string="OD Sphère")
    og_sphere = fields.Char(string="OG Sphère")
    od_cylinder = fields.Char(string="OD Cylindre")
    og_cylinder = fields.Char(string="OG Cylindre")


class ProductTemplate(models.Model):
    _inherit = "product.template"

    optical_product_type = fields.Selection([
        ("glasses", "Verres"),
        ("frames", "Montures"),
        ("contact_lenses", "Lentilles"),
        ("others", "Autres"),
    ], string="Type de produit optique", default="others", required=True)

