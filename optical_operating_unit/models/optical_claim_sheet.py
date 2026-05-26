# -*- coding: utf-8 -*-
from odoo import fields, models


class OpticalClaimSheetOU(models.Model):
    _inherit = 'optical.claim.sheet'

    operating_unit_id = fields.Many2one(
        'operating.unit', string="Unite operationnelle", readonly=True,
    )
