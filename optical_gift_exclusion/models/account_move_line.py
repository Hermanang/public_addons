# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    is_gift = fields.Boolean(
        string="Ligne cadeau (offert)",
        default=False,
        readonly=True,
        copy=False,
        help="Positionne automatiquement depuis is_gift sur la ligne de commande "
             "lors de la generation des factures assurance/TM.",
    )
