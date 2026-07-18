# -*- coding: utf-8 -*-
from odoo import fields, models


class OpticalFollowupLunarDate(models.Model):
    _name = 'optical.followup.lunar.date'
    _description = "Date lunaire hégirienne (référentiel annuel)"
    _order = 'year desc, date_gregorian_start desc, id desc'

    name = fields.Char(string="Nom", required=True)
    year = fields.Integer(string="Année grégorienne", required=True)
    event = fields.Selection(
        [
            ('ramadan_start', "Début du Ramadan"),
            ('aid_fitr', "Aïd al-Fitr"),
            ('aid_adha', "Aïd al-Adha (Tabaski)"),
            ('magal', "Grand Magal de Touba"),
        ],
        string="Événement",
        required=True,
    )
    date_gregorian_start = fields.Date(string="Date grégorienne (début)")
    date_gregorian_end = fields.Date(string="Date grégorienne (fin)")
    source = fields.Char(
        string="Source",
        help="Origine des dates (ex. « MoonSighting.com — validation "
             "manuelle 2026-07-15 »).",
    )
    verified = fields.Boolean(
        string="Vérifié",
        default=True,
        help="À décocher lors d'un audit annuel pour signaler une date à "
             "revérifier avant la période concernée.",
    )

    _sql_constraints = [
        (
            'unique_year_event',
            'unique(year, event)',
            "Un seul enregistrement lunaire par année et événement.",
        ),
    ]
