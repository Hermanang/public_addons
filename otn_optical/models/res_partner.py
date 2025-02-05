# Copyright 2017 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

from odoo import fields, models


class Partner(models.Model):
    _inherit = "res.partner"

    prescription_total = fields.Integer(compute='_prescription_total', string="Prescriptions")

    def action_view_partner_prescriptions(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("otn_optical.action_optical_prescription")
        action['domain'] = [
            ('patient_id', 'in', self.ids)
        ]
        return action

    def _prescription_total(self):
        self.prescription_total = 0
        if not self.ids:
            return True

        for record in self:
            record.prescription_total = (self.env['optical.prescription'].
                search_count([('patient_id', '=', record.id)]))

