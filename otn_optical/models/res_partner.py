# Copyright 2017 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

from odoo import _, api, fields, models, tools


class Partner(models.Model):
    _inherit = "res.partner"

    is_optometrist = fields.Boolean()
    is_health_provident = fields.Boolean()
