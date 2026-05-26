# -*- coding: utf-8 -*-
from odoo import _, fields, models


class OpticalInsurerPlanOU(models.Model):
    _inherit = 'optical.insurer.plan'

    operating_unit_id = fields.Many2one(
        'operating.unit',
        string=_("Unite operationnelle"),
        default=lambda self: self.env['res.users']._get_default_operating_unit(),
        index='btree_not_null',
    )
