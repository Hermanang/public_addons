# -*- coding: utf-8 -*-
from odoo import models


class SaleOrderOU(models.Model):
    _inherit = 'sale.order'

    def action_create_pec(self):
        """Override pour propager l'OU sur la PEC."""
        res = super().action_create_pec()
        if self.pec_id and self.operating_unit_id:
            self.pec_id.operating_unit_id = self.operating_unit_id
        return res

    def action_create_split_invoices(self):
        """Override pour propager l'OU sur les factures split."""
        res = super().action_create_split_invoices()
        if self.operating_unit_id:
            invoices = self.env['account.move'].search([
                ('insurance_sale_order_id', '=', self.id),
                ('move_type', '=', 'out_invoice'),
                ('operating_unit_id', '=', False),
            ])
            if invoices:
                invoices.write({'operating_unit_id': self.operating_unit_id.id})
        return res
