# Copyright 2026 Luxe Optique
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    # Champs relationnels dénormalisés pour l'analyse optique
    optical_subscriber_id = fields.Many2one(
        'res.partner',
        string='Souscripteur',
        compute='_compute_optical_relations',
        store=True,
        help="Entreprise employeur du patient"
    )
    optical_insurance_id = fields.Many2one(
        'res.partner',
        string='Assurance/IPM',
        compute='_compute_optical_relations',
        store=True,
        help="Organisme assureur du patient"
    )
    optical_prescriber_id = fields.Many2one(
        'res.partner',
        string='Prescripteur',
        compute='_compute_optical_relations',
        store=True,
        help="Médecin prescripteur de l'ordonnance"
    )
    optical_clinic_id = fields.Many2one(
        'res.partner',
        string='Cabinet',
        compute='_compute_optical_relations',
        store=True,
        help="Cabinet/clinique du prescripteur"
    )

    @api.depends('partner_id', 'line_ids.sale_line_ids')
    def _compute_optical_relations(self):
        """Calcule les relations optiques depuis les partenaires et prescriptions."""
        if not self:
            return

        Relation = self.env['res.partner.relation']
        today = fields.Date.today()

        # Récupération des types de relations UNE SEULE FOIS (F1, F2 fix)
        employee_type = self.env.ref('otn_optical.relation_type_employee', raise_if_not_found=False)
        works_at_type = self.env.ref('otn_optical.relation_type_works_at', raise_if_not_found=False)
        insurance_type = self.env['res.partner.relation.type'].search(
            [('name', '=', 'est assuré par')], limit=1
        )

        # Pré-charger toutes les relations pertinentes en batch (F3 fix)
        partner_ids = self.mapped('partner_id').ids
        if partner_ids:
            type_ids = [t.id for t in [employee_type, insurance_type] if t]
            all_partner_relations = Relation.search([
                ('left_partner_id', 'in', partner_ids),
                ('type_id', 'in', type_ids),
                '|', ('date_end', '=', False), ('date_end', '>=', today),
                '|', ('date_start', '=', False), ('date_start', '<=', today),
            ]) if type_ids else Relation

            # Indexer les relations par (partner_id, type_id)
            relations_by_partner_type = {}
            for rel in all_partner_relations:
                key = (rel.left_partner_id.id, rel.type_id.id)
                if key not in relations_by_partner_type:
                    relations_by_partner_type[key] = rel
        else:
            relations_by_partner_type = {}

        for move in self:
            subscriber = self.env['res.partner']
            insurance = self.env['res.partner']
            prescriber = self.env['res.partner']
            clinic = self.env['res.partner']

            if move.partner_id:
                # Recherche du souscripteur (employeur) via relation "est employé de"
                if employee_type:
                    rel = relations_by_partner_type.get((move.partner_id.id, employee_type.id))
                    if rel:
                        subscriber = rel.right_partner_id

                # Recherche de l'assurance/IPM via relation "est assuré par"
                if insurance_type:
                    rel = relations_by_partner_type.get((move.partner_id.id, insurance_type.id))
                    if rel:
                        insurance = rel.right_partner_id

            # Recherche du prescripteur via la commande liée (F6 fix - simplifié)
            prescription = move.line_ids.sale_line_ids.order_id.prescription_id[:1]
            if prescription:
                prescriber = prescription.prescriber_id

            # Recherche du cabinet via relation "exerce dans" du prescripteur
            if prescriber and works_at_type:
                clinic_relation = Relation.search([
                    ('left_partner_id', '=', prescriber.id),
                    ('type_id', '=', works_at_type.id),
                    '|', ('date_end', '=', False), ('date_end', '>=', today),
                    '|', ('date_start', '=', False), ('date_start', '<=', today),
                ], limit=1)
                if clinic_relation:
                    clinic = clinic_relation.right_partner_id

            move.optical_subscriber_id = subscriber
            move.optical_insurance_id = insurance
            move.optical_prescriber_id = prescriber
            move.optical_clinic_id = clinic

    def action_recompute_optical_relations(self):
        """Recalcule manuellement les relations optiques.

        Utile si les relations partenaires sont modifiées après la facturation.
        """
        self._compute_optical_relations()
        return True
