# -*- coding: utf-8 -*-
from odoo import fields, models


class OpticalSaleReportOU(models.Model):
    _inherit = 'optical.sale.report'

    operating_unit_id = fields.Many2one(
        'operating.unit', string="Unite operationnelle", readonly=True,
    )

    def _select(self):
        return super()._select() + """,
                    am.operating_unit_id AS operating_unit_id
        """
