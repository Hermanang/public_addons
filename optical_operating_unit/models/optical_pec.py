# -*- coding: utf-8 -*-
from odoo import fields, models


class OpticalPecOU(models.Model):
    _inherit = 'optical.pec'

    operating_unit_id = fields.Many2one(
        'operating.unit',
        string="Unite operationnelle",
        default=lambda self: self.env['res.users']._get_default_operating_unit(),
        index='btree_not_null',
    )

    def action_create_invoices(self):
        """Override pour propager l'OU sur les factures generées."""
        res = super().action_create_invoices()
        order = self.sale_order_id
        if order.operating_unit_id:
            if self.invoice_insurance_id and not self.invoice_insurance_id.operating_unit_id:
                self.invoice_insurance_id.operating_unit_id = order.operating_unit_id
            if self.invoice_tm_id and not self.invoice_tm_id.operating_unit_id:
                self.invoice_tm_id.operating_unit_id = order.operating_unit_id
        return res
