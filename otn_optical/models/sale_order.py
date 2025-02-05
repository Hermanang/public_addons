# Copyright 2017 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

from odoo import fields, models, api


class SaleOrder(models.Model):
    _inherit = "sale.order"

    prescription_id = fields.Many2one('optical.prescription')
    measure_type = fields.Selection([
        ('glasses', 'Lunettes'),
        ('contact_lenses', 'Lentilles'),
    ], string="Type de prescription", compute='_compute_measures_values')

    vision_type = fields.Selection([
        ('far', 'Vision de Loin'),
        ('near', 'Vision de Près'),
        ('intermediate', 'Vision Intermédiaire'),
        ('progressive', 'Progressif')
    ], string="Type de Vision", compute='_compute_measures_values')

    od_sphere = fields.Char(string="OD Sphère", compute='_compute_measures_values')
    og_sphere = fields.Char(string="OG Sphère", compute='_compute_measures_values')
    od_cylinder = fields.Char(string="OD Cylindre", compute='_compute_measures_values')
    og_cylinder = fields.Char(string="OG Cylindre", compute='_compute_measures_values')
    od_axis = fields.Char(string="OD Axe", compute='_compute_measures_values')
    og_axis = fields.Char(string="OG Axe", compute='_compute_measures_values')
    od_addition = fields.Char(string="OD Addition", compute='_compute_measures_values')
    og_addition = fields.Char(string="OG Addition", compute='_compute_measures_values')

    od_prism = fields.Char(string="OD Prisme", compute='_compute_measures_values')
    og_prism = fields.Char(string="OG Prisme", compute='_compute_measures_values')
    od_base = fields.Selection([
        ('inferior', 'Inférieur'),
        ('superior', 'Supérieur'),
        ('nasal', 'Nasale'),
        ('temporal', 'Temporale')
    ], string="OD Base", compute='_compute_measures_values')
    og_base = fields.Selection([
        ('inferior', 'Inférieur'),
        ('superior', 'Supérieur'),
        ('nasal', 'Nasale'),
        ('temporal', 'Temporale')
    ], string="OD Base", compute='_compute_measures_values')

    ep_od = fields.Char(string="Écart Pupillaire OD (mm)", compute='_compute_measures_values')
    ep_og = fields.Char(string="Écart Pupillaire OG (mm)", compute='_compute_measures_values')

    @api.depends('prescription_id')
    def _compute_measures_values(self):
        for order in self:
            if order.prescription_id:
                prescription = order.prescription_id
                order.vision_type = prescription.vision_type
                order.od_sphere = prescription.od_sphere
                order.og_sphere = prescription.og_sphere
                order.od_cylinder = prescription.od_cylinder
                order.og_cylinder = prescription.og_cylinder
                order.od_axis = prescription.od_axis
                order.og_axis = prescription.og_axis
                order.od_addition = prescription.od_addition
                order.og_addition = prescription.og_addition
                order.od_prism = prescription.od_prism
                order.og_prism = prescription.og_prism
                order.od_base = prescription.od_base
                order.og_base = prescription.og_base
                order.ep_od = prescription.ep_od
                order.ep_og = prescription.ep_og
