# Copyright (C) 2023 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AccountMoveLineTag(models.Model):
    _name = "account.move.line.tag"
    _description = "Account Move Line Tag Model"

    name = fields.Char(required=True)
