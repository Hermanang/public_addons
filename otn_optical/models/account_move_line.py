# Copyright 2017 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

from odoo import fields, models, api


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    beneficiary_id = fields.Many2one("res.partner", "Bénéficiaire")
    subscriber = fields.Char("Souscripteur", compute="_compute_subscriber", store=True)
    pec_policy = fields.Char(string="PEC n°/Police")

    @api.depends("beneficiary_id")
    def _compute_subscriber(self):
        for record in self:
            if record.beneficiary_id.parent_id.is_company:
                record.subscriber = record.beneficiary_id.parent_id.name
