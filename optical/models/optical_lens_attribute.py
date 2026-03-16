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
