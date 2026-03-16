# -*- coding: utf-8 -*-
from odoo import fields, models


class ReportDynamicColumnClaim(models.Model):
    _inherit = 'report.dynamic.column'

    default_insurance = fields.Boolean(string='Defaut assurance', default=False)
    default_ipm = fields.Boolean(string='Defaut IPM', default=False)
