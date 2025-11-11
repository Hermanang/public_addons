from odoo import fields, models

class InheritAccountAnalyticPlan(models.Model):
    _inherit = 'account.analytic.plan'

    company_id = fields.Many2one('res.company', string='Company')