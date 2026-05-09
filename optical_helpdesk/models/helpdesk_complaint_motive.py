# -*- coding: utf-8 -*-
from odoo import fields, models


class HelpdeskComplaintMotive(models.Model):
    _name = 'helpdesk.complaint.motive'
    _description = "Motif de réclamation"
    _order = 'sequence, name'

    name = fields.Char(
        string="Motif",
        required=True,
        translate=True,
    )
    sequence = fields.Integer(default=10)
    color = fields.Integer(string="Couleur")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name='res.company',
        string="Société",
        default=lambda self: self.env.company,
    )
