# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.osv import expression
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'
    _description = "Facture (extension optique)"

    is_insurance_invoice = fields.Boolean(
        string="Facture assurance",
        default=False,
        index=True,
        copy=False,
    )
    is_tm_invoice = fields.Boolean(
        string="Ticket modérateur",
        default=False,
        index=True,
        copy=False,
    )
    insurance_policy_id = fields.Many2one(
        'optical.policy',
        string="Police d'assurance",
        readonly=True,
        copy=False,
        index='btree_not_null',
    )
    insurance_sale_order_id = fields.Many2one(
        'sale.order',
        string="Commande d'origine",
        readonly=True,
        copy=False,
        index='btree_not_null',
    )
    pec_id = fields.Many2one(
        'optical.pec',
        string="Prise en charge",
        readonly=True,
        copy=False,
        index='btree_not_null',
        check_company=True,
    )
    patient_name = fields.Char(
        related='pec_id.patient_id.name',
        string="Bénéficiaire",
    )
    pec_partner_ref = fields.Char(
        related='pec_id.partner_ref',
        string="Réf. organisme PEC",
        store=True,
    )
    claim_sheet_id = fields.Many2one(
        'optical.claim.sheet',
        string="Bordereau",
        readonly=True,
        copy=False,
        index=True,
    )
    insurance_sent = fields.Boolean(
        string="Envoyée à l'IPM",
        default=False,
        copy=False,
        index=True,
    )
    insurance_sent_date = fields.Date(
        string="Date envoi IPM",
        copy=False,
        readonly=True,
        index=True,
    )

    # === COMPUTED AGING FIELDS (Story 7-2) === #
    days_overdue = fields.Integer(
        string="Ancienneté (jours)",
        compute='_compute_days_overdue',
        search='_search_days_overdue',
    )
    aging_bucket = fields.Selection(
        [('0_30', '0-30 jours'), ('31_60', '31-60 jours'),
         ('61_90', '61-90 jours'), ('over_90', '> 90 jours')],
        string="Tranche ancienneté",
        compute='_compute_days_overdue',
        search='_search_aging_bucket',
    )

    @api.depends('invoice_date')
    def _compute_days_overdue(self):
        today = fields.Date.context_today(self)
        for move in self:
            if move.invoice_date:
                delta = (today - move.invoice_date).days
                move.days_overdue = max(delta, 0)
            else:
                move.days_overdue = 0
                delta = 0
            if delta <= 30:
                move.aging_bucket = '0_30'
            elif delta <= 60:
                move.aging_bucket = '31_60'
            elif delta <= 90:
                move.aging_bucket = '61_90'
            else:
                move.aging_bucket = 'over_90'

    def _search_days_overdue(self, operator, value):
        today = fields.Date.context_today(self)
        # Inverse: days_overdue <op> value => invoice_date <inverse_op> (today - value)
        inverse_ops = {
            '=': '=', '!=': '!=',
            '<': '>', '>': '<', '<=': '>=', '>=': '<=',
        }
        if operator not in inverse_ops:
            return expression.FALSE_DOMAIN
        target_date = today - timedelta(days=value)
        return [('invoice_date', inverse_ops[operator], target_date)]

    def _search_aging_bucket(self, operator, value):
        today = fields.Date.context_today(self)
        bucket_ranges = {
            '0_30': (0, 30),
            '31_60': (31, 60),
            '61_90': (61, 90),
        }
        if operator == '=' and value == 'over_90':
            return [('invoice_date', '<=', today - timedelta(days=91))]
        if operator == '!=' and value == 'over_90':
            return [('invoice_date', '>', today - timedelta(days=91))]
        if operator == '=' and value in bucket_ranges:
            low, high = bucket_ranges[value]
            return [('invoice_date', '>=', today - timedelta(days=high)),
                    ('invoice_date', '<=', today - timedelta(days=low))]
        if operator == '!=' and value in bucket_ranges:
            low, high = bucket_ranges[value]
            return ['|',
                    ('invoice_date', '<', today - timedelta(days=high)),
                    ('invoice_date', '>', today - timedelta(days=low))]
        return expression.FALSE_DOMAIN

    # === CONSTRAINT METHODS === #
    @api.constrains('insurance_sale_order_id', 'is_insurance_invoice')
    def _check_insurance_traceability(self):
        """NFR11 — Traçabilité obligatoire pour les factures assurance.

        Contrainte conditionnelle : ne se déclenche que sur les factures assurance
        pour ne pas bloquer les factures non-optiques (NFR15).
        """
        for move in self.filtered('is_insurance_invoice'):
            if not move.insurance_sale_order_id:
                raise ValidationError(
                    _("Une facture assurance doit être liée à une commande d'origine "
                      "(chaîne de traçabilité obligatoire).")
                )

    def unlink(self):
        optical_moves = self.filtered(lambda m: m.is_insurance_invoice or m.is_tm_invoice)
        if not optical_moves:
            return super().unlink()

        # Bloquer si au moins une facture optique n'est pas en brouillon
        non_draft = optical_moves.filtered(lambda m: m.state != 'draft')
        if non_draft:
            raise UserError(
                _("La suppression des factures assurance et tickets modérateurs "
                  "n'est autorisée qu'à l'état brouillon. "
                  "Utilisez un avoir pour les factures validées.")
            )

        # Rassembler le couple complet (assurance + TM) pour suppression couplée
        siblings = self.env['account.move']
        for move in optical_moves:
            if move.pec_id:
                siblings |= move.pec_id.invoice_insurance_id | move.pec_id.invoice_tm_id
            elif move.insurance_sale_order_id:
                siblings |= self.search([
                    ('insurance_sale_order_id', '=', move.insurance_sale_order_id.id),
                    ('move_type', '=', 'out_invoice'),
                    ('id', '!=', move.id),
                    '|', ('is_insurance_invoice', '=', True),
                    ('is_tm_invoice', '=', True),
                ])
        all_optical = optical_moves | siblings

        # Vérifier que le couple entier est en brouillon
        non_draft_siblings = all_optical.filtered(lambda m: m.state != 'draft')
        if non_draft_siblings:
            raise UserError(
                _("Impossible de supprimer : la facture jumelle (%s) est validée. "
                  "Utilisez un avoir pour annuler puis supprimer les factures validées.",
                  ', '.join(non_draft_siblings.mapped('name')))
            )

        # Nettoyer les PEC liées avant suppression
        pecs = all_optical.mapped('pec_id').filtered(lambda p: p.state == 'invoiced')
        if pecs:
            pecs.write({
                'state': 'approved',
                'invoice_insurance_id': False,
                'invoice_tm_id': False,
            })
            _logger.info(
                "PEC nettoyées après suppression factures brouillon : %s → approved",
                ', '.join(pecs.mapped('name')),
            )

        # Fusionner les siblings dans le batch — super() explicite avec
        # AccountMove + self rebound pour que le MRO utilise le recordset élargi.
        _logger.info(
            "Suppression couplée factures brouillon : %s (ids=%s)",
            ', '.join(n or 'draft' for n in all_optical.mapped('name')),
            all_optical.ids,
        )
        self = self | all_optical
        return super(AccountMove, self).unlink()

    # === ACTION METHODS (Story 7-1) === #
    def action_mark_insurance_sent(self):
        """FR36 — Marquer les factures assurance comme envoyées à l'IPM.

        Supporte le marquage individuel et groupé.
        Réservé au groupe optical.group_optical_manager (AC6).
        """
        if not self:
            return
        if not self.env.user.has_group('optical.group_optical_manager'):
            raise UserError(_("Seul un responsable optique peut marquer les factures comme envoyées."))
        non_insurance = self.filtered(lambda m: not m.is_insurance_invoice)
        if non_insurance:
            raise UserError(_("Seules les factures assurance peuvent être marquées comme envoyées à l'IPM."))
        non_posted = self.filtered(lambda m: m.state != 'posted')
        if non_posted:
            raise UserError(_("Seules les factures validées peuvent être marquées comme envoyées."))
        to_send = self.filtered(lambda m: not m.insurance_sent)
        if not to_send:
            return
        today = fields.Date.context_today(self)
        to_send.sudo().write({
            'insurance_sent': True,
            'insurance_sent_date': today,
        })
        # message_post n'est pas batch-compatible dans Odoo — N appels inévitables
        for move in to_send.sudo():
            move.message_post(body=_("Facture marquée comme envoyée à l'IPM le %s.", today))

    def action_unmark_insurance_sent(self):
        """Annuler le marquage envoi IPM. Réservé au responsable."""
        if not self:
            return
        if not self.env.user.has_group('optical.group_optical_manager'):
            raise UserError(_("Seul un responsable optique peut annuler le marquage envoi."))
        non_insurance = self.filtered(lambda m: not m.is_insurance_invoice)
        if non_insurance:
            raise UserError(_("Seules les factures assurance peuvent être démarquées."))
        non_posted = self.filtered(lambda m: m.state != 'posted')
        if non_posted:
            raise UserError(_("Seules les factures validées peuvent être démarquées."))
        # Tracer la dissociation sur les bordereaux AVANT de vider le lien
        claim_sheets = self.sudo().mapped('claim_sheet_id')
        for sheet in claim_sheets:
            invoices_in_sheet = self.filtered(lambda m: m.claim_sheet_id == sheet)
            sheet.message_post(body=_(
                "Factures dissociées du bordereau : %s",
                ', '.join(invoices_in_sheet.mapped('name')),
            ))
        self.sudo().write({
            'insurance_sent': False,
            'insurance_sent_date': False,
            'claim_sheet_id': False,
        })
        # message_post n'est pas batch-compatible dans Odoo — N appels inévitables
        for move in self.sudo():
            move.message_post(body=_("Marquage envoi IPM annulé."))
