# -*- coding: utf-8 -*-
from odoo import fields, models


class OpticalClaimSheetColumns(models.Model):
    _inherit = 'optical.claim.sheet'

    column_ids = fields.Many2many(
        'report.dynamic.column',
        relation='claim_sheet_dynamic_column_rel',
        column1='claim_sheet_id', column2='column_id',
        string='Colonnes du rapport',
        readonly=True,
    )

    def _get_report_columns(self):
        """Retourne les colonnes a utiliser pour le rendu, avec fallback.

        Si column_ids est vide (bordereaux crées avant l'installation du
        bridge), toutes les colonnes actives claim_sheet sont utilisées.
        """
        self.ensure_one()
        if self.column_ids:
            return self.column_ids
        return self.env['report.dynamic.column'].search([
            ('report_type', '=', 'claim_sheet'),
            ('active', '=', True),
        ], order='sequence, id')

    def _get_column_value(self, column, invoice, line=None):
        """Mapping technical_name vers données du bordereau."""
        mapping = {
            'date': invoice.invoice_date,
            'reference': invoice.name or '',
            'subscriber': (
                invoice.pec_id.policy_id.subscriber_id.name
                if invoice.pec_id.policy_id.subscriber_id else ''
            ),
            'participant': invoice.pec_id.patient_id.name or '',
            'beneficiary': invoice.pec_id.patient_id.name or '',
            'partner_ref': invoice.pec_id.partner_ref or '',
            'pec_number': invoice.pec_id.name or '',
            'policy_number': invoice.pec_id.policy_id.name or '',
            'product_name': line.product_id.name if line else '',
            'optical_type': (
                dict(
                    line.product_id.product_tmpl_id._fields['optical_type']
                    ._description_selection(self.env)
                ).get(line.product_id.optical_type, '')
                if line and line.product_id.optical_type else ''
            ),
            'amount_untaxed': line.price_subtotal if line else 0.0,
            'amount_total': line.price_total if line else 0.0,
            'amount_tax': (line.price_total - line.price_subtotal) if line else 0.0,
        }
        return mapping.get(column.technical_name, '')

    # Colonnes dont la valeur varie par ligne de produit (pas par facture)
    _PER_LINE_COLUMNS = {
        'product_name', 'optical_type',
        'amount_untaxed', 'amount_total', 'amount_tax',
    }

    def _get_dynamic_rows(self):
        """Genere les rows dynamiques pour le template QWeb a partir des column_ids.

        Les colonnes communes a une facture (date, reference, beneficiaire...)
        sont fusionnées via rowspan sur la premiere ligne produit.
        """
        self.ensure_one()
        columns = self._get_report_columns()
        if not columns:
            return []
        groups = self._get_invoices_grouped()
        rows = []
        grand_total_values = [0.0] * len(columns)

        for group in groups:
            subtotal_values = [0.0] * len(columns)
            for invoice in group['invoices']:
                product_lines = self._get_invoice_product_lines(invoice)
                line_count = len(product_lines)
                for line_idx, line in enumerate(product_lines):
                    row_values = []
                    rowspans = []
                    cell_subtitles = {}
                    for i, col in enumerate(columns):
                        val = self._get_column_value(col, invoice, line)
                        row_values.append(val)
                        if col.is_subtotalable and isinstance(val, (int, float)):
                            subtotal_values[i] += val
                        # Colonnes par facture : rowspan sur la 1ere ligne, 0 (skip) apres
                        if col.technical_name not in self._PER_LINE_COLUMNS:
                            rowspans.append(line_count if line_idx == 0 else 0)
                        else:
                            rowspans.append(1)
                        # Sous-titre TVA inline pour montures
                        if (col.technical_name == 'amount_total'
                                and line and line.price_total != line.price_subtotal):
                            cell_subtitles[i] = {
                                'label': 'DONT TVA',
                                'amount': line.price_total - line.price_subtotal,
                            }
                    row_data = {'values': row_values, 'rowspans': rowspans}
                    if cell_subtitles:
                        row_data['cell_subtitles'] = cell_subtitles
                    rows.append(row_data)

            st_label = (
                'SOUS TOTAL CLIENT'
                if self.insurer_id.insurer_type == 'insurance'
                else 'SOUS TOTAL'
            )
            st_row = []
            for i, col in enumerate(columns):
                if col.is_subtotalable:
                    st_row.append(subtotal_values[i])
                    grand_total_values[i] += subtotal_values[i]
                elif i == 0:
                    st_row.append(st_label)
                else:
                    st_row.append('')
            rows.append({'values': st_row, 'is_subtotal': True})

        total_row = []
        for i, col in enumerate(columns):
            if col.is_subtotalable:
                total_row.append(grand_total_values[i])
            elif i == 0:
                total_row.append('TOTAL GENERAL')
            else:
                total_row.append('')
        rows.append({'values': total_row, 'is_total': True})

        return rows
