# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, tools


class OpticalSaleReport(models.Model):
    _name = 'optical.sale.report'
    _description = "Rapport des ventes optiques"
    _auto = False
    _order = 'date desc'

    # --- Dimensions ---
    date = fields.Date(string="Date", readonly=True)
    month = fields.Selection([
        ('01', 'Janvier'), ('02', 'Fevrier'), ('03', 'Mars'),
        ('04', 'Avril'), ('05', 'Mai'), ('06', 'Juin'),
        ('07', 'Juillet'), ('08', 'Aout'), ('09', 'Septembre'),
        ('10', 'Octobre'), ('11', 'Novembre'), ('12', 'Decembre'),
    ], string="Mois", readonly=True)
    year = fields.Integer(string="Annee", readonly=True)
    insurer_id = fields.Many2one('res.partner', string="Assureur / IPM", readonly=True)
    prescriber_id = fields.Many2one('res.partner', string="Prescripteur", readonly=True)
    subscriber_id = fields.Many2one('res.partner', string="Souscripteur", readonly=True)
    patient_id = fields.Many2one('res.partner', string="Patient", readonly=True)
    optical_type = fields.Selection([
        ('frame', 'Monture'),
        ('lens', 'Verre'),
        ('contact_lens', 'Lentille de contact'),
        ('accessory', 'Accessoire'),
        ('service', 'Service'),
    ], string="Type optique", readonly=True)
    policy_id = fields.Many2one('optical.policy', string="Police", readonly=True)
    pec_id = fields.Many2one('optical.pec', string="PEC", readonly=True)
    product_id = fields.Many2one('product.product', string="Produit", readonly=True)
    product_tmpl_id = fields.Many2one('product.template', string="Modele produit", readonly=True)
    company_id = fields.Many2one('res.company', string="Societe", readonly=True)
    is_insurance_invoice = fields.Boolean(string="Facture assurance", readonly=True)

    # --- Proprietes produit ---
    frame_shape = fields.Selection([
        ('rectangular', 'Rectangulaire'),
        ('oval', 'Ovale'),
        ('square', 'Carre'),
        ('browline', 'Browline'),
        ('aviator', 'Aviateur'),
        ('round', 'Rond'),
        ('butterfly', 'Papillon'),
        ('geometric', 'Geometrique'),
        ('heart', 'Coeur'),
    ], string="Forme monture", readonly=True)
    frame_gender = fields.Selection([
        ('man', 'Homme'),
        ('woman', 'Femme'),
        ('mixed', 'Mixte'),
        ('boy', 'Garcon'),
        ('girl', 'Fille'),
    ], string="Genre monture", readonly=True)
    frame_rim_type = fields.Selection([
        ('full_rim', 'Cerclee'),
        ('semi_rimless', 'Semi-cerclee'),
        ('rimless', 'Non cerclee'),
    ], string="Type cerclage", readonly=True)
    lens_design = fields.Selection([
        ('single_vision', 'Unifocal'),
        ('progressive', 'Progressif'),
        ('bifocal', 'Bifocal'),
        ('degressive', 'Degressif'),
        ('mid_distance', 'Mi-distance'),
    ], string="Design verre", readonly=True)
    lens_material = fields.Selection([
        ('organic', 'Organique'),
        ('polycarbonate', 'Polycarbonate'),
        ('mineral', 'Minerale'),
        ('trivex', 'Trivex'),
    ], string="Materiau verre", readonly=True)
    lens_surface = fields.Selection([
        ('spherical', 'Spherique'),
        ('aspherical', 'Aspherique'),
        ('double_aspherical', 'Double aspherique'),
        ('freeform', 'Freeform'),
    ], string="Surface verre", readonly=True)
    lens_index = fields.Char(string="Indice refraction", readonly=True)
    frame_materials = fields.Char(string="Materiaux monture", readonly=True)
    frame_colors = fields.Char(string="Couleurs monture", readonly=True)
    lens_treatments = fields.Char(string="Traitements verre", readonly=True)
    lens_tints = fields.Char(string="Teintes verre", readonly=True)

    # --- Mesures ---
    amount_total = fields.Float(string="Montant TTC", readonly=True)
    amount_untaxed = fields.Float(string="Montant HT", readonly=True)
    product_qty = fields.Float(string="Quantite", readonly=True)
    nbr = fields.Integer(string="Nombre de lignes", readonly=True)

    def _select(self):
        return """
                    aml.id AS id,
                    am.invoice_date AS date,
                    TO_CHAR(am.invoice_date, 'MM') AS month,
                    EXTRACT(YEAR FROM am.invoice_date)::integer AS year,
                    -- Dimensions assureur / prescripteur / souscripteur
                    op.insurer_id AS insurer_id,
                    oprescr.prescriber_id AS prescriber_id,
                    opol.subscriber_id AS subscriber_id,
                    op.patient_id AS patient_id,
                    -- Produit
                    aml.product_id AS product_id,
                    pp.product_tmpl_id AS product_tmpl_id,
                    pt.optical_type AS optical_type,
                    -- Proprietes produit
                    pt.frame_shape AS frame_shape,
                    pt.frame_gender AS frame_gender,
                    pt.frame_rim_type AS frame_rim_type,
                    pt.lens_design AS lens_design,
                    pt.lens_material AS lens_material,
                    pt.lens_surface AS lens_surface,
                    oli.name AS lens_index,
                    (SELECT string_agg(attr.name, ', ' ORDER BY attr.name)
                     FROM optical_frame_material_product_template_rel rel
                     JOIN optical_frame_material attr ON attr.id = rel.optical_frame_material_id
                     WHERE rel.product_template_id = pt.id
                    ) AS frame_materials,
                    (SELECT string_agg(attr.name, ', ' ORDER BY attr.name)
                     FROM optical_frame_color_product_template_rel rel
                     JOIN optical_frame_color attr ON attr.id = rel.optical_frame_color_id
                     WHERE rel.product_template_id = pt.id
                    ) AS frame_colors,
                    (SELECT string_agg(attr.name, ', ' ORDER BY attr.name)
                     FROM optical_lens_treatment_product_template_rel rel
                     JOIN optical_lens_treatment attr ON attr.id = rel.optical_lens_treatment_id
                     WHERE rel.product_template_id = pt.id
                    ) AS lens_treatments,
                    (SELECT string_agg(attr.name, ', ' ORDER BY attr.name)
                     FROM optical_lens_tint_product_template_rel rel
                     JOIN optical_lens_tint attr ON attr.id = rel.optical_lens_tint_id
                     WHERE rel.product_template_id = pt.id
                    ) AS lens_tints,
                    -- Organisation
                    am.company_id AS company_id,
                    am.is_insurance_invoice AS is_insurance_invoice,
                    op.id AS pec_id,
                    opol.id AS policy_id,
                    -- Mesures
                    aml.price_total AS amount_total,
                    aml.price_subtotal AS amount_untaxed,
                    aml.quantity AS product_qty,
                    1 AS nbr
        """

    def _from(self):
        return """
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                JOIN product_product pp ON pp.id = aml.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN optical_lens_index oli ON oli.id = pt.lens_index_id
                LEFT JOIN optical_pec op ON op.id = am.pec_id
                LEFT JOIN optical_policy opol ON opol.id = op.policy_id
                LEFT JOIN optical_prescription oprescr ON oprescr.id = op.prescription_id
        """

    def _where(self):
        return """
                WHERE am.state = 'posted'
                  AND aml.display_type = 'product'
        """

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT %s %s %s
            )
        """ % (self._table, self._select(), self._from(), self._where()))
