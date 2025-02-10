# Copyright 2017 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

from odoo import fields, models, api


class SaleOrder(models.Model):
    _inherit = "sale.order"

    prescription_id = fields.Many2one("optical.prescription", domain="[('patient_id', '=', partner_id)]")
    measure_type = fields.Selection([
        ("glasses", "Verres"),
        ("contact_lenses", "Lentilles"),
    ], string="Type de prescription", related="prescription_id.measure_type", store=True)

    vision_type = fields.Selection([
        ("far", "Vision de Loin"),
        ("near", "Vision de Près"),
        ("intermediate", "Vision Intermédiaire"),
        ("progressive", "Progressif")
    ], string="Type de Vision", related="prescription_id.vision_type", store=True)
    treatment = fields.Selection([
        ('antireflective', 'Antireflet'),
        ('progressive', 'Progressif'),
        ('photochromic', 'Photochromique'),
        ('organic', 'Organiques')
    ], string="Traitement", related="prescription_id.treatment", store=True)

    od_sphere = fields.Char(string="OD Sphère", related="prescription_id.od_sphere", store=True)
    og_sphere = fields.Char(string="OG Sphère", related="prescription_id.og_sphere", store=True)
    od_cylinder = fields.Char(string="OD Cylindre", related="prescription_id.od_cylinder", store=True)
    og_cylinder = fields.Char(string="OG Cylindre", related="prescription_id.og_cylinder", store=True)
    od_axis = fields.Char(string="OD Axe", related="prescription_id.od_axis", store=True)
    og_axis = fields.Char(string="OG Axe", related="prescription_id.og_axis", store=True)
    od_addition = fields.Char(string="OD Addition", related="prescription_id.od_addition", store=True)
    og_addition = fields.Char(string="OG Addition", related="prescription_id.og_addition", store=True)

    od_prism = fields.Char(
        string="OD Prisme",
        related="prescription_id.od_prism",
        store=True
    )
    og_prism = fields.Char(string="OG Prisme", related="prescription_id.og_prism")
    od_base = fields.Selection([
        ("inferior", "Inférieur"),
        ("superior", "Supérieur"),
        ("nasal", "Nasale"),
        ("temporal", "Temporale")
    ], string="OD Base", related="prescription_id.od_base")
    og_base = fields.Selection([
        ("inferior", "Inférieur"),
        ("superior", "Supérieur"),
        ("nasal", "Nasale"),
        ("temporal", "Temporale")
    ], string="OG Base", related="prescription_id.og_base")

    ep_gl = fields.Char(
        string="Écart Pupillaire Globale (mm)",
        related="prescription_id.ep_gl",
        store=True
    )
    ep_od = fields.Char(
        string="Écart Pupillaire OD (mm)",
        related="prescription_id.ep_od",
        store=True
    )
    ep_og = fields.Char(
        string="Écart Pupillaire OG (mm)",
        related="prescription_id.ep_og",
        store=True
    )

