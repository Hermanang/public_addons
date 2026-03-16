# -*- coding: utf-8 -*-
from num2words import num2words

from odoo import models
from odoo.tools import is_html_empty
from odoo.tools.mail import html2plaintext


class OpticalClaimSheet(models.Model):
    _inherit = 'optical.claim.sheet'

    def _get_tax_summary(self):
        """Ventilation fiscale excluant les lignes is_gift.

        Override de optical.claim.sheet._get_tax_summary()
        (extra-addons/optical/models/optical_claim_sheet.py:199).
        Logique identique à la méthode de base sauf le filtre
        ``and not l.is_gift`` sur les lignes facture.
        Maintenir en sync si la méthode de base évolue.
        """
        self.ensure_one()
        exempt_amount = 0.0
        taxed_base = 0.0
        legal_notes = set()
        tax_map = {}
        for invoice in self.invoice_ids:
            for line in invoice.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product' and not l.is_gift
            ):
                if not line.tax_ids or all(
                    t.amount == 0 for t in line.tax_ids
                ):
                    exempt_amount += line.price_subtotal
                    for t in line.tax_ids:
                        if not is_html_empty(t.invoice_legal_notes):
                            legal_notes.add(
                                html2plaintext(t.invoice_legal_notes).strip()
                            )
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

    def _get_invoices_grouped(self):
        """Regroupe les factures en excluant les lignes is_gift des subtotals.

        Override de optical.claim.sheet._get_invoices_grouped()
        (extra-addons/optical/models/optical_claim_sheet.py:267).
        Recalcule le subtotal par groupe en sommant price_total des lignes
        non-gift au lieu d'utiliser invoice.amount_total_signed.
        Maintenir en sync si la méthode de base évolue.
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
            non_gift_lines = invoice.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product' and not l.is_gift
            )
            # price_total est toujours positif — appliquer le signe de la
            # facture (négatif pour les avoirs) comme le fait amount_total_signed.
            sign = -1 if invoice.move_type in ('out_refund', 'in_refund') else 1
            groups[key]['subtotal'] += sign * sum(
                non_gift_lines.mapped('price_total')
            )
        return list(groups.values())

    def _get_invoice_product_lines(self, invoice):
        """Override du hook : exclut les lignes cadeau (is_gift=True).

        Surcharge optical.claim.sheet._get_invoice_product_lines()
        (extra-addons/optical/models/optical_claim_sheet.py).
        Utilisé notamment par optical_report_columns._get_dynamic_rows()
        pour ne pas afficher les lignes cadeau dans le bordereau colonnes.
        """
        lines = super()._get_invoice_product_lines(invoice)
        return lines.filtered(lambda l: not l.is_gift)

    def _amount_to_text(self, amount):
        """Convertit un montant arbitraire en lettres (français, FCFA).

        Utilisé par le template QWeb hérité pour afficher le total
        hors cadeaux en lettres (au lieu de self.amount_total).
        """
        self.ensure_one()
        amount = int(round(amount))
        if amount == 0:
            return "ZERO FRANC CFA"
        negative = amount < 0
        amount = abs(amount)
        text = num2words(amount, lang='fr').upper()
        suffix = " FRANC CFA" if amount == 1 else " FRANCS CFA"
        if negative:
            return "MOINS " + text + suffix
        return text + suffix
