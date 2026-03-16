# -*- coding: utf-8 -*-
import logging
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ClaimSheetWizard(models.TransientModel):
    _name = 'optical.claim.sheet.wizard'
    _description = "Assistant generation bordereau"

    insurer_id = fields.Many2one(
        'res.partner',
        string="Assureur / IPM",
        required=True,
        domain="[('is_insurer', '=', True)]",
    )
    date_from = fields.Date(
        string="Du",
        required=True,
        default=lambda self: date.today().replace(day=1) - relativedelta(months=1),
    )
    date_to = fields.Date(
        string="Au",
        required=True,
        default=lambda self: date.today().replace(day=1) - timedelta(days=1),
    )
    type = fields.Selection([
        ('normal', 'Normal'),
        ('complementary', 'Complementaire'),
        ('rectificative', 'Rectificatif'),
    ], string="Type", default='normal', required=True)
    parent_id = fields.Many2one(
        'optical.claim.sheet', string="Bordereau d'origine",
        domain="[('insurer_id', '=', insurer_id), ('state', '=', 'generated')]",
    )
    invoice_ids = fields.Many2many(
        'account.move',
        string="Factures",
        readonly=True,
    )

    @api.constrains('type', 'parent_id')
    def _check_parent_required(self):
        for rec in self:
            if rec.type != 'normal' and not rec.parent_id:
                raise ValidationError(
                    _("Le bordereau d'origine est obligatoire pour un bordereau complementaire ou rectificatif.")
                )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_to < rec.date_from:
                raise ValidationError(
                    _("La date de fin doit etre posterieure ou egale a la date de debut.")
                )

    def _get_invoice_domain(self):
        """Construit le domain de recherche des factures eligibles."""
        domain = [
            ('is_insurance_invoice', '=', True),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('insurance_sent', '=', False),
            ('partner_id', '=', self.insurer_id.id),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
        ]
        return domain

    def action_search_invoices(self):
        """Recherche les factures eligibles pour le bordereau."""
        self.ensure_one()
        invoices = self.env['account.move'].search(self._get_invoice_domain())
        if not invoices:
            raise UserError(
                _("Aucune facture a inclure dans le bordereau pour cet assureur et cette periode.")
            )
        self.write({'invoice_ids': [fields.Command.set(invoices.ids)]})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_generate(self):
        """Genere le bordereau PDF et marque les factures comme envoyees."""
        self.ensure_one()
        if not self.invoice_ids:
            raise UserError(_("Aucune facture selectionnee. Lancez la recherche d'abord."))
        # Verification doublon : un bordereau identique actif existe deja ?
        existing = self.env['optical.claim.sheet'].search([
            ('insurer_id', '=', self.insurer_id.id),
            ('date_from', '=', self.date_from),
            ('date_to', '=', self.date_to),
            ('type', '=', self.type),
            ('state', '=', 'generated'),
        ], limit=1)
        if existing:
            raise UserError(_(
                "Un bordereau de type '%(type)s' existe deja pour cet assureur "
                "sur cette periode (%(ref)s).",
                type=dict(self._fields['type']._description_selection(self.env)).get(self.type, self.type),
                ref=existing.name,
            ))
        # Creer le bordereau persistant (catch race condition sur contrainte SQL)
        try:
            claim_sheet = self.env['optical.claim.sheet'].create({
                'insurer_id': self.insurer_id.id,
                'date_from': self.date_from,
                'date_to': self.date_to,
                'type': self.type,
                'parent_id': self.parent_id.id or False,
            })
        except IntegrityError:
            raise UserError(_(
                "Un bordereau de ce type existe deja pour cet assureur sur cette periode "
                "(creation concurrente detectee)."
            )) from None
        # Lier les factures et les marquer (sudo car droits account)
        self.invoice_ids.sudo().write({
            'insurance_sent': True,
            'insurance_sent_date': fields.Date.context_today(self),
            'claim_sheet_id': claim_sheet.id,
        })
        _logger.info(
            "Bordereau %s genere: assureur=%s, periode=%s-%s, %d factures, user=%s",
            claim_sheet.name, self.insurer_id.name, self.date_from, self.date_to,
            len(self.invoice_ids), self.env.user.login,
        )
        return self.env.ref('optical.action_report_claim_sheet').report_action(claim_sheet)

