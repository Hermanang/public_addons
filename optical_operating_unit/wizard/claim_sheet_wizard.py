# -*- coding: utf-8 -*-

from odoo import fields, models


class ClaimSheetWizardOU(models.TransientModel):
    _inherit = 'optical.claim.sheet.wizard'

    operating_unit_id = fields.Many2one(
        'operating.unit',
        string="Unite operationnelle",
    )

    def _get_invoice_domain(self):
        domain = super()._get_invoice_domain()
        if self.operating_unit_id:
            domain.append(('operating_unit_id', '=', self.operating_unit_id.id))
        return domain

    def action_generate(self):
        res = super().action_generate()
        if self.operating_unit_id and self.invoice_ids:
            claim_sheet = self.invoice_ids[:1].claim_sheet_id
            if claim_sheet:
                claim_sheet.operating_unit_id = self.operating_unit_id
        return res
