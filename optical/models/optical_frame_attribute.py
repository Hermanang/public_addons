# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from random import randint

from odoo import fields, models


class OpticalFrameMaterial(models.Model):
    _name = 'optical.frame.material'
    _description = "Matériau de monture optique"
    _order = 'sequence, name'

    name = fields.Char(string="Nom", required=True)
    sequence = fields.Integer(string="Séquence", default=10)
    active = fields.Boolean(string="Actif", default=True)
    color = fields.Integer(string="Couleur", default=lambda self: randint(1, 11))

    _sql_constraints = [
        ('name_uniq', 'unique(name)', "Un matériau avec ce nom existe déjà."),
    ]


class OpticalFrameColor(models.Model):
    _name = 'optical.frame.color'
    _description = "Couleur de monture optique"
    _order = 'sequence, name'

    name = fields.Char(string="Nom", required=True)
    sequence = fields.Integer(string="Séquence", default=10)
    active = fields.Boolean(string="Actif", default=True)
    color = fields.Integer(string="Couleur", default=lambda self: randint(1, 11))

    _sql_constraints = [
        ('name_uniq', 'unique(name)', "Une couleur avec ce nom existe déjà."),
    ]


class OpticalFrameUsage(models.Model):
    _name = 'optical.frame.usage'
    _description = "Usage de monture optique"
    _order = 'sequence, name'

    name = fields.Char(string="Nom", required=True)
    sequence = fields.Integer(string="Séquence", default=10)
    active = fields.Boolean(string="Actif", default=True)
    color = fields.Integer(string="Couleur", default=lambda self: randint(1, 11))

    _sql_constraints = [
        ('name_uniq', 'unique(name)', "Un usage avec ce nom existe déjà."),
    ]
