# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class OpticalCoverageRule(models.Model):
    _name = 'optical.coverage.rule'
    _description = "Règle de couverture par catégorie"
    _order = 'sequence, product_category'

    plan_id = fields.Many2one(
        'optical.insurer.plan',
        string="Plan de couverture",
        required=True,
        ondelete='cascade',
        index='btree_not_null',
    )
    product_category = fields.Selection(
        [
            ('frame', "Monture"),
            ('lens', "Verre"),
            ('contact_lens', "Lentille de contact"),
            ('accessory', "Accessoire"),
        ],
        string="Catégorie produit",
        required=True,
    )
    coverage_rate = fields.Float(
        string="Taux de couverture (%)",
        required=True,
    )
    reference_price = fields.Monetary(
        string="Tarif de référence",
        currency_field='currency_id',
    )
    annual_ceiling = fields.Monetary(
        string="Plafond annuel",
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='plan_id.company_id.currency_id',
    )
    company_id = fields.Many2one(
        related='plan_id.company_id',
        store=True,
    )
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    _sql_constraints = [
        (
            'plan_category_unique',
            'unique(plan_id, product_category)',
            "Une seule règle par catégorie de produit par plan.",
        ),
    ]

    @api.constrains('coverage_rate')
    def _check_coverage_rate(self):
        for record in self:
            if record.coverage_rate < 0 or record.coverage_rate > 100:
                raise ValidationError(
                    _("Le taux de couverture doit être compris entre 0 et 100.")
                )
