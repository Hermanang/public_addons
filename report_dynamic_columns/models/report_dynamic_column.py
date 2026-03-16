# -*- coding: utf-8 -*-
from odoo import fields, models


class ReportDynamicColumn(models.Model):
    _name = 'report.dynamic.column'
    _description = 'Colonne dynamique de rapport'
    _order = 'sequence, id'

    name = fields.Char(string='Nom', required=True, translate=True)
    technical_name = fields.Char(string='Nom technique', required=True)
    report_type = fields.Char(string='Type de rapport', required=True, index=True)
    sequence = fields.Integer(string='Séquence', default=10)
    figure_type = fields.Selection([
        ('text', 'Texte'),
        ('monetary', 'Monétaire'),
        ('date', 'Date'),
        ('integer', 'Entier'),
        ('float', 'Décimal'),
    ], string='Type de valeur', default='text', required=True)
    alignment = fields.Selection([
        ('left', 'Gauche'),
        ('center', 'Centre'),
        ('right', 'Droite'),
    ], string='Alignement', default='left', required=True)
    is_subtotalable = fields.Boolean(string='Sous-totalisable', default=False)
    active = fields.Boolean(string='Actif', default=True)

    _sql_constraints = [
        ('unique_technical_name_report_type',
         'UNIQUE(technical_name, report_type)',
         'Le nom technique doit être unique par type de rapport.'),
    ]
