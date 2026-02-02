# Copyright 2017 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

from odoo import _, api, fields, models, tools


class Partner(models.Model):
    _inherit = "res.partner"

    is_health_provident = fields.Boolean()
    is_clinical = fields.Boolean(string="Est une clinique ?")
    prescription_total = fields.Integer(compute='_prescription_total', string="Prescriptions")

    # Champs prescripteur
    is_prescriber = fields.Boolean(
        string="Est prescripteur",
        compute='_compute_is_prescriber',
        help="Indique si ce contact a émis au moins une prescription optique"
    )
    prescriber_invoice_count = fields.Integer(
        string="Nb factures (prescripteur)",
        compute='_compute_prescriber_invoices',
        help="Nombre de factures générées par les patients de ce prescripteur"
    )
    prescriber_total_ht = fields.Monetary(
        string="CA prescripteur HT",
        compute='_compute_prescriber_invoices',
        currency_field='currency_id',
        help="Chiffre d'affaires HT généré par les patients de ce prescripteur"
    )

    def _compute_is_prescriber(self):
        """Détermine si le contact est un prescripteur (a émis au moins une prescription)."""
        for partner in self:
            partner.is_prescriber = False

        partner_ids = [p.id for p in self if p.id]
        if not partner_ids:
            return

        # Une seule requête SQL pour tous les partenaires
        results = self.env['optical.prescription']._read_group(
            [('prescriber_id', 'in', partner_ids)],
            groupby=['prescriber_id'],
            aggregates=['__count'],
        )

        prescriber_ids = {prescriber.id for prescriber, count in results}

        for partner in self:
            if partner.id in prescriber_ids:
                partner.is_prescriber = True

    def _compute_prescriber_invoices(self):
        """Calcule le nombre de factures et le CA HT pour chaque prescripteur.

        Utilise _read_group pour une agrégation performante en une seule requête SQL.
        """
        for partner in self:
            partner.prescriber_invoice_count = 0
            partner.prescriber_total_ht = 0.0

        partner_ids = [p.id for p in self if p.id]
        if not partner_ids:
            return

        domain = [
            ('optical_prescriber_id', 'in', partner_ids),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
            ('company_id', '=', self.env.company.id),
        ]

        results = self.env['account.move']._read_group(
            domain,
            groupby=['optical_prescriber_id'],
            aggregates=['__count', 'amount_untaxed_signed:sum'],
        )

        totals_by_partner = {
            prescriber.id: (count, amount_sum or 0.0)
            for prescriber, count, amount_sum in results
        }

        for partner in self:
            if partner.id in totals_by_partner:
                count, amount = totals_by_partner[partner.id]
                partner.prescriber_invoice_count = count
                partner.prescriber_total_ht = amount

    def action_view_prescriber_invoices(self):
        """Ouvre la liste des factures générées par les patients de ce prescripteur."""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_move_out_invoice_type")
        action['domain'] = [
            ('optical_prescriber_id', '=', self.id),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
            ('company_id', '=', self.env.company.id),
        ]
        action['context'] = {
            'default_move_type': 'out_invoice',
        }
        return action

    def action_view_partner_prescriptions(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("otn_optical.action_optical_prescription")
        action['domain'] = [
            ('patient_id', 'in', self.ids)
        ]
        return action

    def _prescription_total(self):
        self.prescription_total = 0
        if not self.ids:
            return True

        for record in self:
            record.prescription_total = (self.env['optical.prescription'].
                                         search_count([('patient_id', '=', record.id)]))

