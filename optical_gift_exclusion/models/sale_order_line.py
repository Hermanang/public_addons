# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_gift = fields.Boolean(
        string="Cadeau (offert)",
        default=False,
        help="Cocher pour marquer cette ligne comme cadeau/offert. "
             "Les lignes cadeaux sont exclues du bordereau assurance. "
             "Si le module sale_loyalty est installe, les lignes reward "
             "sont automatiquement marquées comme cadeaux.",
    )

    def write(self, vals):
        res = super().write(vals)
        # Synchro automatique : si sale_loyalty positionne is_reward_line=True,
        # propager vers is_gift (sauf si is_gift est deja explicitement positionne)
        if vals.get('is_reward_line') and 'is_gift' not in vals:
            self.filtered(lambda l: not l.is_gift).is_gift = True
        return res
