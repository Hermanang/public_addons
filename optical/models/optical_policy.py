# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class OpticalPolicy(models.Model):
    _name = 'optical.policy'
    _description = "Police d'assurance optique"
    _inherit = ['mail.thread.main.attachment', 'mail.activity.mixin']
    _order = 'date_end desc, id desc'

    # === FIELDS === #
    name = fields.Char(
        string="Référence",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('Nouveau'),
        index='trigram',
    )
    patient_id = fields.Many2one(
        'res.partner',
        string="Patient",
        required=True,
        domain="[('is_patient', '=', True)]",
        index='btree_not_null',
        tracking=True,
        check_company=True,
    )
    insurer_id = fields.Many2one(
        'res.partner',
        string="Assureur/IPM",
        required=True,
        domain="[('is_insurer', '=', True)]",
        index='btree_not_null',
        tracking=True,
        check_company=True,
    )
    subscriber_id = fields.Many2one(
        'res.partner',
        string="Souscripteur",
        index='btree_not_null',
        tracking=True,
        check_company=True,
    )
    beneficiary_relationship = fields.Selection(
        [
            ('holder', "Titulaire"),
            ('spouse', "Conjoint"),
            ('child', "Enfant"),
            ('parent', "Parent"),
            ('other', "Autre"),
        ],
        string="Relation bénéficiaire",
        default='holder',
        tracking=True,
    )
    member_number = fields.Char(
        string="Numéro d'adhérent",
        index='trigram',
        tracking=True,
    )
    plan_id = fields.Many2one(
        'optical.insurer.plan',
        string="Plan de couverture",
        index='btree_not_null',
        tracking=True,
        check_company=True,
    )
    coverage_rate = fields.Float(
        string="Taux de couverture (%)",
        default=80.0,
        tracking=True,
    )
    date_start = fields.Date(
        string="Date de début",
        tracking=True,
    )
    date_end = fields.Date(
        string="Date de fin",
        tracking=True,
    )
    state = fields.Selection(
        [
            ('active', 'Active'),
            ('expired', 'Expiré'),
            ('cancelled', 'Annulée'),
        ],
        string="État",
        default='active',
        required=True,
        tracking=True,
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string="Société",
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string="Devise",
        related='company_id.currency_id',
    )
    active = fields.Boolean(default=True)

    # === COMPUTED FIELDS === #
    amount_consumed = fields.Monetary(
        string="Montant consommé",
        compute='_compute_consumption',
        store=False,
        currency_field='currency_id',
    )
    amount_remaining = fields.Monetary(
        string="Montant restant",
        compute='_compute_consumption',
        store=False,
        currency_field='currency_id',
    )
    annual_cap_total = fields.Monetary(
        string="Plafond annuel total",
        compute='_compute_consumption',
        store=False,
        currency_field='currency_id',
    )

    # === COMPUTE METHODS === #
    def _compute_consumption(self):
        """Calcule le montant consommé, restant et le plafond annuel total (FR22)."""
        today = fields.Date.context_today(self)
        year_start = today.replace(month=1, day=1)
        year_end = today.replace(month=12, day=31)

        # Agrégation en une seule requête SQL (évite N+1)
        consumed_map = {}
        if self.ids:
            groups = self.env['account.move']._read_group(
                domain=[
                    ('is_insurance_invoice', '=', True),
                    ('insurance_policy_id', 'in', self.ids),
                    ('state', '=', 'posted'),
                    ('date', '>=', year_start),
                    ('date', '<=', year_end),
                ],
                groupby=['insurance_policy_id'],
                aggregates=['amount_total:sum'],
            )
            consumed_map = {policy.id: total for policy, total in groups}

        for policy in self:
            # Plafond annuel total = somme des annual_ceiling des règles du plan
            cap = sum(
                policy.plan_id.coverage_rule_ids.mapped('annual_ceiling')
            ) if policy.plan_id else 0.0

            consumed = consumed_map.get(policy.id, 0.0)

            policy.annual_cap_total = cap
            policy.amount_consumed = consumed
            policy.amount_remaining = cap - consumed

    # === ONCHANGE === #
    @api.onchange('patient_id')
    def _onchange_patient_id(self):
        if self.patient_id and self.patient_id.parent_id:
            self.subscriber_id = self.patient_id.parent_id

    @api.onchange('plan_id')
    def _onchange_plan_id(self):
        if self.plan_id:
            self.coverage_rate = self.plan_id.default_coverage_rate

    # === CONSTRAINT METHODS === #
    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for record in self:
            if record.date_start and record.date_end and record.date_end <= record.date_start:
                raise ValidationError(
                    _("La date de fin doit être postérieure à la date de début.")
                )

    # === CRUD OVERRIDES === #
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('Nouveau'):
                vals['name'] = self.env['ir.sequence'].next_by_code('optical.policy') or _('Nouveau')
        return super().create(vals_list)

    def unlink(self):
        raise UserError(_("La suppression n'est pas autorisée. Utilisez l'archivage."))

    # === CRON METHODS === #
    def _cron_expire_policies(self):
        """Cron : expire les polices actives dont la date de fin est dépassée (FR23)."""
        today = fields.Date.context_today(self)
        expired = self.search([
            ('state', '=', 'active'),
            ('date_end', '<', today),
        ])
        if expired:
            expired.write({'state': 'expired'})
            _logger.info("Cron expiration polices : %d police(s) expirée(s).", len(expired))
