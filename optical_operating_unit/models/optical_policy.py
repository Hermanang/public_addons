# -*- coding: utf-8 -*-
from odoo import fields, models


class OpticalPolicyOU(models.Model):
    _inherit = 'optical.policy'

    operating_unit_id = fields.Many2one(
        'operating.unit',
        string="Unite operationnelle",
        default=lambda self: self.env['res.users']._get_default_operating_unit(),
        index='btree_not_null',
    )
