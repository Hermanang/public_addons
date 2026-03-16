# -*- coding: utf-8 -*-
import logging

from num2words import num2words

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import is_html_empty
from odoo.tools.mail import html2plaintext

_logger = logging.getLogger(__name__)


class OpticalClaimSheet(models.Model):
    _name = 'optical.claim.sheet'
    _description = "Bordereau"
    _inherit = ['mail.thread']
    _order = 'name desc'

    name = fields.Char(
        string="Reference",
        readonly=True,
        copy=False,
        default=lambda self: _('Nouveau'),
        index='trigram',
        tracking=True,
    )
    insurer_id = fields.Many2one(
        'res.partner', string="Assureur / IPM",
        required=True, readonly=True, index=True,
        domain="[('is_insurer', '=', True)]",
    )
    date_from = fields.Date(string="Du", required=True, readonly=True)
    date_to = fields.Date(string="Au", required=True, readonly=True)
    date_generated = fields.Date(
        string="Date de generation",
        default=fields.Date.context_today, readonly=True,
    )
    user_id = fields.Many2one(
        'res.users', string="Genere par",
        default=lambda self: self.env.user, readonly=True,
    )

    # Lien factures (One2many via claim_sheet_id sur account.move)
    invoice_ids = fields.One2many(
        'account.move', 'claim_sheet_id', string="Factures", readonly=True,
    )
    invoice_count = fields.Integer(compute='_compute_totals')
    amount_total = fields.Monetary(
        string="Total", compute='_compute_totals',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id,
        readonly=True,
    )

    # Etat du bordereau (generated / cancelled)
    state = fields.Selection([
        ('generated', 'Généré'),
        ('cancelled', 'Annulé'),
    ], string="État", default='generated', required=True, readonly=True,
        tracking=True)

    # Type (normal / complementaire / rectificatif)
    type = fields.Selection([
        ('normal', 'Normal'),
        ('complementary', 'Complementaire'),
        ('rectificative', 'Rectificatif'),
    ], string="Type", default='normal', readonly=True)
    parent_id = fields.Many2one(
        'optical.claim.sheet', string="Bordereau d'origine", readonly=True,
    )

    # Computed depuis les factures — pas de gestion manuelle
    amount_paid = fields.Monetary(
        string="Montant recu", compute='_compute_payment_status',
        currency_field='currency_id',
    )
    amount_residual = fields.Monetary(
        string="Reste a recevoir", compute='_compute_payment_status',
        currency_field='currency_id',
    )
    is_fully_paid = fields.Boolean(
        string="Entierement paye", compute='_compute_payment_status',
        search='_search_is_fully_paid',
    )

    def init(self):
        super().init()
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
                optical_claim_sheet_unique_insurer_period_type_generated
            ON optical_claim_sheet (insurer_id, date_from, date_to, type)
            WHERE state = 'generated'
        """)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nouveau')) == _('Nouveau'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'optical.claim.sheet'
                ) or _('Nouveau')
        return super().create(vals_list)

    def unlink(self):
        raise UserError(_("Les bordereaux ne peuvent pas etre supprimes."))

    def write(self, vals):
        # invoice_ids (One2many) n'est PAS protege ici car les ecritures
        # passent par account.move.write(claim_sheet_id=...), pas par ce write().
        protected = {'insurer_id', 'date_from', 'date_to'}
        if protected & set(vals.keys()):
            raise UserError(
                _("Les bordereaux ne peuvent pas etre modifies apres generation.")
            )
        return super().write(vals)

    def action_cancel(self):
        """Annuler le bordereau et libérer les factures associées."""
        self.ensure_one()
        if not self.env.user.has_group('optical.group_optical_manager'):
            raise UserError(
                _("Seul un responsable optique peut annuler un bordereau.")
            )
        if self.state != 'generated':
            raise UserError(
                _("Seuls les bordereaux en état 'Généré' peuvent être annulés.")
            )
        if self.amount_paid > 0:
            raise UserError(
                _("Impossible d'annuler un bordereau avec des paiements reçus "
                  "(montant reçu : %(amount)s).",
                  amount=self.amount_paid)
            )
        # Capturer les réfs factures AVANT de casser le lien One2many
        invoices = self.invoice_ids
        invoice_names = ', '.join(invoices.mapped('name'))
        invoice_count = len(invoices)
        # Libérer les factures
        invoices.sudo().write({
            'insurance_sent': False,
            'insurance_sent_date': False,
            'claim_sheet_id': False,
        })
        # Passer en état annulé
        self.sudo().write({'state': 'cancelled'})
        # Poster un message dans le chatter
        self.message_post(body=_(
            "Bordereau annulé. %(count)d facture(s) libérée(s) : %(names)s",
            count=invoice_count,
            names=invoice_names or _("aucune"),
        ))

    @api.depends('invoice_ids', 'invoice_ids.amount_total_signed')
    def _compute_totals(self):
        for sheet in self:
            sheet.invoice_count = len(sheet.invoice_ids)
            sheet.amount_total = sum(
                sheet.invoice_ids.mapped('amount_total_signed')
            )

    def _compute_payment_status(self):
        # Pas de @api.depends intentionnel : les champs dependent de payment_state
        # et amount_residual_signed qui changent via le lettrage bancaire (reconciliation).
        # La chaine de depends serait fragile et declencherait des recalculs en cascade.
        # Sans depends, le compute est execute a chaque acces — acceptable car la
        # consultation des bordereaux est peu frequente.
        for sheet in self:
            invoices = sheet.invoice_ids
            sheet.amount_paid = sum(
                inv.amount_total_signed - inv.amount_residual_signed
                for inv in invoices
            )
            sheet.amount_residual = sum(
                invoices.mapped('amount_residual_signed')
            )
            sheet.is_fully_paid = bool(invoices) and all(
                inv.payment_state == 'paid' for inv in invoices
            )

    def _search_is_fully_paid(self, operator, value):
        """Recherche les bordereaux entierement payes ou non (SQL performant)."""
        self.env.cr.execute("""
            SELECT cs.id
            FROM optical_claim_sheet cs
            WHERE EXISTS (
                SELECT 1 FROM account_move am WHERE am.claim_sheet_id = cs.id
            )
            AND NOT EXISTS (
                SELECT 1 FROM account_move am2
                WHERE am2.claim_sheet_id = cs.id
                  AND am2.payment_state != 'paid'
            )
        """)
        paid_ids = [r[0] for r in self.env.cr.fetchall()]
        if (operator == '=' and value) or (operator == '!=' and not value):
            return [('id', 'in', paid_ids)]
        return [('id', 'not in', paid_ids)]

    def _get_tax_summary(self):
        """Ventilation fiscale dynamique du bordereau.

        Regroupe les lignes par taxe appliquee et retourne :
        - exempt_amount : total des lignes exonerées (sans taxe ou taxe 0%)
        - taxes : liste de dicts {name, rate, base, tax_amount} par taxe non-nulle
        - legal_notes : set de mentions legales (invoice_legal_notes) des taxes 0%
        - amount_total : total general
        """
        self.ensure_one()
        exempt_amount = 0.0
        taxed_base = 0.0
        legal_notes = set()
        tax_map = {}  # tax.id -> {name, rate, base, tax_amount}
        for invoice in self.invoice_ids:
            for line in invoice.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product'
            ):
                if not line.tax_ids or all(
                    t.amount == 0 for t in line.tax_ids
                ):
                    exempt_amount += line.price_subtotal
                    for t in line.tax_ids:
                        if not is_html_empty(t.invoice_legal_notes):
                            legal_notes.add(html2plaintext(t.invoice_legal_notes).strip())
                else:
                    taxed_base += line.price_subtotal
                    line_tax_amount = line.price_total - line.price_subtotal
                    for tax in line.tax_ids:
                        if tax.id not in tax_map:
                            tax_map[tax.id] = {
                                'name': tax.name,
                                'rate': tax.amount,
                                'base': 0.0,
                                'tax_amount': 0.0,
                            }
                        tax_map[tax.id]['base'] += line.price_subtotal
                        tax_map[tax.id]['tax_amount'] += line_tax_amount
        taxes = sorted(tax_map.values(), key=lambda t: t['rate'])
        total = exempt_amount + taxed_base + sum(
            t['tax_amount'] for t in taxes
        )
        return {
            'exempt_amount': exempt_amount,
            'taxes': taxes,
            'legal_notes': legal_notes,
            'amount_total': total,
        }

    def amount_to_text(self):
        """Convertit le montant total en lettres (francais, FCFA)."""
        self.ensure_one()
        amount = int(round(self.amount_total))
        if amount == 0:
            return "ZERO FRANC CFA"
        negative = amount < 0
        amount = abs(amount)
        text = num2words(amount, lang='fr').upper()
        suffix = " FRANC CFA" if amount == 1 else " FRANCS CFA"
        if negative:
            return "MOINS " + text + suffix
        return text + suffix

    def _get_invoices_grouped(self):
        """Regroupe les factures selon le type d'assureur.

        - Format Assurance : regroupement par souscripteur (employeur)
        - Format IPM : regroupement par beneficiaire (patient)
        """
        self.ensure_one()
        is_insurance = self.insurer_id.insurer_type == 'insurance'
        groups = {}
        for invoice in self.invoice_ids:
            patient = invoice.pec_id.patient_id
            subscriber = invoice.pec_id.policy_id.subscriber_id
            if is_insurance:
                key = subscriber.id or patient.id
                group_label = subscriber.name or patient.name
            else:
                key = patient.id
                group_label = patient.name
            if key not in groups:
                groups[key] = {
                    'patient': patient,
                    'subscriber': subscriber,
                    'group_label': group_label,
                    'invoices': self.env['account.move'],
                    'subtotal': 0.0,
                }
            groups[key]['invoices'] |= invoice
            groups[key]['subtotal'] += invoice.amount_total_signed
        return list(groups.values())

    def _get_invoice_product_lines(self, invoice):
        """Retourne les lignes produit d'une facture à inclure dans le bordereau.

        Hook destiné à être surchargé par les modules bridge pour affiner
        le filtre (ex. exclusion des lignes cadeau, filtrage par type...).
        """
        return invoice.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product'
        )
