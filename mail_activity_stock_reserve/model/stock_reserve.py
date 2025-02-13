# Copyright 2013 Camptocamp SA - Guewen Baconnier
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import models


class StockReservation(models.Model):
    _name = "stock.reservation"
    _inherit = ['stock.reservation', 'mail.thread', 'mail.activity.mixin']
