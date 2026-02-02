# Copyright 2026 Luxe Optique
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

from odoo import api, fields, models
from odoo.tools import SQL


class OpticalSaleProductReport(models.Model):
    """Rapport d'analyse des ventes par propriétés produit optique."""

    _name = "report.optical.sale.product"
    _description = "Analyse des ventes par propriétés produit"
    _auto = False
    _rec_name = 'invoice_date'
    _order = 'invoice_date desc'

    # Champs facture
    invoice_date = fields.Date(string='Date facture', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Client', readonly=True)
    move_id = fields.Many2one('account.move', string='Facture', readonly=True)
    company_id = fields.Many2one('res.company', string='Société', readonly=True)

    # Champs produit optique
    product_id = fields.Many2one('product.product', string='Produit', readonly=True)
    optical_product_type = fields.Selection([
        ('lenses', 'Verres'),
        ('frames', 'Montures'),
        ('contact_lenses', 'Lentilles'),
        ('others', 'Autres'),
    ], string='Type produit optique', readonly=True)
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
    ], string='Forme monture', readonly=True)
    frame_gender = fields.Selection([
        ('man', 'Homme'),
        ('woman', 'Femme'),
        ('mixed', 'Mixte'),
        ('boy', 'Garçon'),
        ('girl', 'Fille'),
    ], string='Genre', readonly=True)
    frame_rim_type = fields.Selection([
        ('rimless', 'Non cerclée'),
        ('semi_rimless', 'Semi-cerclée'),
        ('full_rim', 'Cerclée'),
    ], string='Type cercle', readonly=True)
    lens_material = fields.Selection([
        ('organic', 'Organique'),
        ('polycarbonate', 'Polycarbonate'),
        ('mineral', 'Minérale'),
    ], string='Matière verre', readonly=True)

    # Mesures
    quantity = fields.Float(string='Quantité', readonly=True)
    price_subtotal = fields.Float(string='CA HT', readonly=True)
    price_total = fields.Float(string='CA TTC', readonly=True)

    @property
    def _table_query(self) -> SQL:
        return SQL('%s %s %s', self._select(), self._from(), self._where())

    @api.model
    def _select(self) -> SQL:
        return SQL('''
            SELECT
                line.id AS id,
                move.invoice_date AS invoice_date,
                move.partner_id AS partner_id,
                move.id AS move_id,
                move.company_id AS company_id,
                line.product_id AS product_id,
                template.optical_product_type AS optical_product_type,
                template.frame_shape AS frame_shape,
                template.frame_gender AS frame_gender,
                template.frame_rim_type AS frame_rim_type,
                template.lens_material AS lens_material,
                line.quantity AS quantity,
                line.price_subtotal AS price_subtotal,
                line.price_total AS price_total
        ''')

    @api.model
    def _from(self) -> SQL:
        return SQL('''
            FROM account_move_line line
            JOIN account_move move ON move.id = line.move_id
            LEFT JOIN product_product product ON product.id = line.product_id
            LEFT JOIN product_template template ON template.id = product.product_tmpl_id
        ''')

    @api.model
    def _where(self) -> SQL:
        return SQL('''
            WHERE move.move_type IN ('out_invoice', 'out_refund')
            AND move.state = 'posted'
            AND line.display_type = 'product'
        ''')


class OpticalSaleInsuranceReport(models.Model):
    """Rapport d'analyse des ventes par assurance/IPM."""

    _name = "report.optical.sale.insurance"
    _description = "Analyse des ventes par assurance/IPM"
    _auto = False
    _rec_name = 'invoice_date'
    _order = 'invoice_date desc'

    # Champs facture
    invoice_date = fields.Date(string='Date facture', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Client', readonly=True)
    move_id = fields.Many2one('account.move', string='Facture', readonly=True)
    company_id = fields.Many2one('res.company', string='Société', readonly=True)

    # Champ assurance
    insurance_id = fields.Many2one('res.partner', string='Assurance/IPM', readonly=True)

    # Mesures
    quantity = fields.Float(string='Quantité', readonly=True)
    price_subtotal = fields.Float(string='CA HT', readonly=True)
    price_total = fields.Float(string='CA TTC', readonly=True)
    nbr_customers = fields.Integer(string='Nb clients', readonly=True)

    @property
    def _table_query(self) -> SQL:
        return SQL('%s %s %s', self._select(), self._from(), self._where())

    @api.model
    def _select(self) -> SQL:
        return SQL('''
            SELECT
                line.id AS id,
                move.invoice_date AS invoice_date,
                move.partner_id AS partner_id,
                move.id AS move_id,
                move.company_id AS company_id,
                move.optical_insurance_id AS insurance_id,
                line.quantity AS quantity,
                line.price_subtotal AS price_subtotal,
                line.price_total AS price_total,
                1 AS nbr_customers
        ''')

    @api.model
    def _from(self) -> SQL:
        return SQL('''
            FROM account_move_line line
            JOIN account_move move ON move.id = line.move_id
        ''')

    @api.model
    def _where(self) -> SQL:
        return SQL('''
            WHERE move.move_type IN ('out_invoice', 'out_refund')
            AND move.state = 'posted'
            AND line.display_type = 'product'
        ''')


class OpticalSalePrescriberReport(models.Model):
    """Rapport d'analyse des ventes par prescripteur/cabinet."""

    _name = "report.optical.sale.prescriber"
    _description = "Analyse des ventes par prescripteur"
    _auto = False
    _rec_name = 'invoice_date'
    _order = 'invoice_date desc'

    # Champs facture
    invoice_date = fields.Date(string='Date facture', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Client', readonly=True)
    move_id = fields.Many2one('account.move', string='Facture', readonly=True)
    company_id = fields.Many2one('res.company', string='Société', readonly=True)

    # Champs prescripteur
    prescriber_id = fields.Many2one('res.partner', string='Prescripteur', readonly=True)
    clinic_id = fields.Many2one('res.partner', string='Cabinet', readonly=True)

    # Mesures
    quantity = fields.Float(string='Quantité', readonly=True)
    price_subtotal = fields.Float(string='CA HT', readonly=True)
    price_total = fields.Float(string='CA TTC', readonly=True)
    nbr_customers = fields.Integer(string='Nb clients', readonly=True)

    @property
    def _table_query(self) -> SQL:
        return SQL('%s %s %s', self._select(), self._from(), self._where())

    @api.model
    def _select(self) -> SQL:
        return SQL('''
            SELECT
                line.id AS id,
                move.invoice_date AS invoice_date,
                move.partner_id AS partner_id,
                move.id AS move_id,
                move.company_id AS company_id,
                move.optical_prescriber_id AS prescriber_id,
                move.optical_clinic_id AS clinic_id,
                line.quantity AS quantity,
                line.price_subtotal AS price_subtotal,
                line.price_total AS price_total,
                1 AS nbr_customers
        ''')

    @api.model
    def _from(self) -> SQL:
        return SQL('''
            FROM account_move_line line
            JOIN account_move move ON move.id = line.move_id
        ''')

    @api.model
    def _where(self) -> SQL:
        return SQL('''
            WHERE move.move_type IN ('out_invoice', 'out_refund')
            AND move.state = 'posted'
            AND line.display_type = 'product'
        ''')


class OpticalSaleSubscriberReport(models.Model):
    """Rapport d'analyse des ventes par souscripteur (employeur)."""

    _name = "report.optical.sale.subscriber"
    _description = "Analyse des ventes par souscripteur"
    _auto = False
    _rec_name = 'invoice_date'
    _order = 'invoice_date desc'

    # Champs facture
    invoice_date = fields.Date(string='Date facture', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Client', readonly=True)
    move_id = fields.Many2one('account.move', string='Facture', readonly=True)
    company_id = fields.Many2one('res.company', string='Société', readonly=True)

    # Champ souscripteur
    subscriber_id = fields.Many2one('res.partner', string='Souscripteur', readonly=True)

    # Mesures
    quantity = fields.Float(string='Quantité', readonly=True)
    price_subtotal = fields.Float(string='CA HT', readonly=True)
    price_total = fields.Float(string='CA TTC', readonly=True)
    nbr_customers = fields.Integer(string='Nb clients', readonly=True)

    @property
    def _table_query(self) -> SQL:
        return SQL('%s %s %s', self._select(), self._from(), self._where())

    @api.model
    def _select(self) -> SQL:
        return SQL('''
            SELECT
                line.id AS id,
                move.invoice_date AS invoice_date,
                move.partner_id AS partner_id,
                move.id AS move_id,
                move.company_id AS company_id,
                move.optical_subscriber_id AS subscriber_id,
                line.quantity AS quantity,
                line.price_subtotal AS price_subtotal,
                line.price_total AS price_total,
                1 AS nbr_customers
        ''')

    @api.model
    def _from(self) -> SQL:
        return SQL('''
            FROM account_move_line line
            JOIN account_move move ON move.id = line.move_id
        ''')

    @api.model
    def _where(self) -> SQL:
        return SQL('''
            WHERE move.move_type IN ('out_invoice', 'out_refund')
            AND move.state = 'posted'
            AND line.display_type = 'product'
        ''')
