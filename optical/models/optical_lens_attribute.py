# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from random import randint

from odoo import fields, models


class OpticalLensTreatment(models.Model):
    _name = 'optical.lens.treatment'
    _description = "Traitement de verre optique"
    _order = 'sequence, name'

    name = fields.Char(string="Nom", required=True)
    sequence = fields.Integer(string="Séquence", default=10)
    active = fields.Boolean(string="Actif", default=True)
    color = fields.Integer(string="Couleur", default=lambda self: randint(1, 11))
    treatment_type = fields.Selection(
        [
            ('base', 'Traitement de base'),
            ('complement', 'Traitement complémentaire'),
        ],
        string="Catégorie",
        help=(
            "« Base » = traitement principal du verre "
            "(photochromique, polarisé, blue-cut…).\n\n"
            "« Complément » = traitement additionnel de finition "
            "(antireflet, mirror, durcisseur…).\n\n"
            "Utilisé pour scinder les traitements en 2 sections "
            "dans le wizard vente et le snapshot ligne."
        ),
    )

    _sql_constraints = [
        ('name_uniq', 'unique(name)', "Un traitement avec ce nom existe déjà."),
    ]


class OpticalLensTint(models.Model):
    _name = 'optical.lens.tint'
    _description = "Teinte de verre optique"
    _order = 'sequence, name'

    name = fields.Char(string="Nom", required=True)
    sequence = fields.Integer(string="Séquence", default=10)
    active = fields.Boolean(string="Actif", default=True)
    color = fields.Integer(string="Couleur", default=lambda self: randint(1, 11))

    _sql_constraints = [
        ('name_uniq', 'unique(name)', "Une teinte avec ce nom existe déjà."),
    ]


class OpticalLensThickness(models.Model):
    _name = 'optical.lens.thickness'
    _description = "Épaisseur de verre optique"
    _order = 'sequence, name'

    name = fields.Char(string="Nom", required=True)
    sequence = fields.Integer(string="Séquence", default=10)
    active = fields.Boolean(string="Actif", default=True)
    color = fields.Integer(string="Couleur", default=lambda self: randint(1, 11))

    _sql_constraints = [
        ('name_uniq', 'unique(name)', "Une épaisseur avec ce nom existe déjà."),
    ]


class OpticalLensIndex(models.Model):
    """Indice de réfraction de verre optique (Story 19-2).

    Diverge volontairement du pattern treatment/tint/thickness :
    - `_order='value'` pour tri numérique fiable (1.50, 1.56, 1.60...)
    - Contrainte unique sur `value` (peu importe le libellé marketing)
    - Pas de champ `color` (indice affiché en dropdown numérique, pas
      en many2many_tags coloré)
    """
    _name = 'optical.lens.index'
    _description = "Indice de réfraction de verre"
    _order = 'value'

    name = fields.Char(
        string="Nom",
        required=True,
        help="Libellé affiché — ex. '1.60' ou '1.60 – Aminci'",
    )
    value = fields.Float(
        string="Valeur",
        required=True,
        digits=(3, 2),
        help="Valeur numérique de l'indice — utilisée pour le tri et le mapping des verres",
    )
    sequence = fields.Integer(string="Séquence", default=10)
    active = fields.Boolean(string="Actif", default=True)

    _sql_constraints = [
        ('value_uniq', 'unique(value)', "Un indice avec cette valeur existe déjà."),
    ]
