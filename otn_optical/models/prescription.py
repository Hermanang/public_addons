# Copyright 2017 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

from odoo import _, fields, models, api


class Prescription(models.Model):
    _name = "optical.prescription"
    _inherit = 'mail.thread'

    def _prescriber_id_domain(self):
        category_id = self.env.ref('otn_optical.partner_category_clinical').id
        return [('category_id', '=', category_id)]

    name = fields.Char(
        string="Reference",
        required=True, copy=False, readonly=False,
        index='trigram',
        default=lambda self: _('New'))
    prescriber_id = fields.Many2one(
        comodel_name='res.partner', string='Prescripteur',
        domain=_prescriber_id_domain)

    patient_id = fields.Many2one(
        comodel_name='res.partner', string='Patient',
        domain="[('is_company','=',False)]")

    prescription_date = fields.Date(string="Prescription date", required=True)
    measure_date = fields.Date(string="Date de la mesure", required=True)
    measure_type = fields.Selection([
        ('glasses', 'Lunettes'),
        ('contact_lenses', 'Lentilles'),
    ], string="Type de prescription", required=True)

    vision_type = fields.Selection([
        ('far', 'Vision de Loin'),
        ('near', 'Vision de Près'),
        ('intermediate', 'Vision Intermédiaire'),
        ('progressive', 'Progressif')
    ], string="Type de Vision", required=True)

    od_sphere = fields.Char(string="OD Sphère")
    og_sphere = fields.Char(string="OG Sphère")
    od_cylinder = fields.Char(string="OD Cylindre")
    og_cylinder = fields.Char(string="OG Cylindre")
    od_axis = fields.Char(string="OD Axe")
    og_axis = fields.Char(string="OG Axe")
    od_addition = fields.Char(string="OD Addition")
    og_addition = fields.Char(string="OG Addition")

    od_prism = fields.Char(string="OD Prisme")
    og_prism = fields.Char(string="OG Prisme")
    od_base = fields.Selection([
        ('inferior', 'Inférieur'),
        ('superior', 'Supérieur'),
        ('nasal', 'Nasale'),
        ('temporal', 'Temporale')
    ], string="OD Base")
    og_base = fields.Selection([
        ('up', 'Haut'),
        ('down', 'Bas'),
        ('in', 'Intérieur'),
        ('out', 'Extérieur')
    ], string="OG Base")

    ep_od = fields.Char(string="Écart Pupillaire OD (mm)")
    ep_og = fields.Char(string="Écart Pupillaire OG (mm)")

    notes = fields.Text(string="Notes")
    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True, index=True,
        default=lambda self: self.env.company)

    # === CRUD METHODS ===#

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _("New")) == _("New"):
                vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code(
                    'optical.prescription') or _("New")

        return super().create(vals_list)

    @api.onchange('od_sphere', 'og_sphere', 'od_cylinder', 'og_cylinder', 'od_addition', 'og_addition', 'od_prism', 'og_prism')
    def _onchange_add_operator(self):
        """Ajoute automatiquement un + devant la valeur si aucun opérateur n'est défini."""
        for field in ['od_sphere', 'og_sphere', 'od_cylinder', 'og_cylinder', 'od_addition', 'og_addition', 'od_prism', 'og_prism']:
            value = getattr(self, field)
            if value and not value.startswith(('+', '-')):  # Si pas d'opérateur défini
                setattr(self, field, f"+{value}")


