# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ReportDynamicColumnProfile(models.Model):
    _name = 'report.dynamic.column.profile'
    _description = 'Profil de colonnes de rapport'

    name = fields.Char(string='Nom', required=True)
    report_type = fields.Char(string='Type de rapport', required=True, index=True)
    column_ids = fields.Many2many(
        'report.dynamic.column',
        string='Colonnes',
    )
    is_default = fields.Boolean(string='Par défaut', default=False)
    partner_id = fields.Many2one('res.partner', string='Organisme', ondelete='set null')

    @api.constrains('is_default', 'report_type', 'partner_id')
    def _check_unique_default(self):
        for profile in self:
            if profile.is_default and not profile.partner_id:
                existing = self.search([
                    ('is_default', '=', True),
                    ('report_type', '=', profile.report_type),
                    ('partner_id', '=', False),
                    ('id', '!=', profile.id),
                ])
                if existing:
                    raise ValidationError(
                        'Un seul profil par défaut est autorisé par type de rapport.'
                    )
