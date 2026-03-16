# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class OpticalInsurerPlan(models.Model):
    _name = 'optical.insurer.plan'
    _description = _("Plan de couverture assurance")
    _order = 'sequence, name'
    _check_company = True

    name = fields.Char(
        string=_("Nom du plan"),
        required=True,
        index='trigram',
    )
    insurer_id = fields.Many2one(
        'res.partner',
        string=_("Assureur/IPM"),
        required=True,
        domain="[('is_insurer', '=', True)]",
        index='btree_not_null',
        check_company=True,
    )
    default_coverage_rate = fields.Float(
        string=_("Taux de couverture par défaut (%)"),
        default=80.0,
    )
    billing_mode = fields.Selection(
        [
            ('third_party', _("Tiers payant")),
            ('reimbursement', _("Remboursement")),
        ],
        string=_("Mode de facturation"),
        default='third_party',
        required=True,
    )
    coverage_rule_ids = fields.One2many(
        'optical.coverage.rule',
        'plan_id',
        string=_("Règles de couverture"),
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
    )
    sequence = fields.Integer(default=10)
    notes = fields.Html(string=_("Notes"))

    @api.constrains('default_coverage_rate')
    def _check_default_coverage_rate(self):
        for record in self:
            if record.default_coverage_rate < 0 or record.default_coverage_rate > 100:
                raise ValidationError(
                    _("Le taux de couverture par défaut doit être compris entre 0 et 100.")
                )

    @api.depends('name', 'insurer_id')
    def _compute_display_name(self):
        for record in self:
            if record.insurer_id:
                record.display_name = f"{record.name} ({record.insurer_id.name})"
            else:
                record.display_name = record.name or ''
