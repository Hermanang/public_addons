# -*- coding: utf-8 -*-
from odoo import fields, models, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    birthdate = fields.Date(
        string="Date de naissance",
    )
    is_patient = fields.Boolean(
        string="Patient optique",
        default=False,
        index=True,
    )
    is_insurer = fields.Boolean(
        string="Assureur/IPM",
        default=False,
        index=True,
    )
    insurer_type = fields.Selection(
        [('insurance', "Assurance"), ('ipm', "IPM")],
        string="Type assureur",
        default='ipm',
    )
    is_prescriber = fields.Boolean(
        string="Prescripteur",
        default=False,
        index=True,
    )
    prescriber_registration = fields.Char(
        string="N° d'enregistrement",
        help="Numero d'enregistrement professionnel du prescripteur",
    )
    prescriber_specialty = fields.Selection(
        [
            ('ophthalmologist', "Ophtalmologue"),
            ('optometrist', "Optometriste"),
            ('other', "Autre"),
        ],
        string="Specialite",
        help="Specialite du prescripteur",
    )

    # --- Dossier patient : One2many inverses ---
    prescription_ids = fields.One2many(
        'optical.prescription', 'patient_id',
        string="Ordonnances",
    )
    policy_ids = fields.One2many(
        'optical.policy', 'patient_id',
        string="Polices d'assurance",
    )

    # --- Souscripteur : One2many inverse ---
    subscriber_policy_ids = fields.One2many(
        'optical.policy', 'subscriber_id',
        string="Polices souscrites",
    )

    # --- Dossier patient : Computed counts pour smart buttons ---
    prescription_count = fields.Integer(
        string="Nombre d'ordonnances",
        compute='_compute_prescription_count',
    )
    policy_count = fields.Integer(
        string="Nombre de polices",
        compute='_compute_policy_count',
    )
    subscriber_policy_count = fields.Integer(
        string="Nombre de polices souscrites",
        compute='_compute_subscriber_policy_count',
    )

    def _compute_prescription_count(self):
        data = self.env['optical.prescription']._read_group(
            [('patient_id', 'in', self.ids)],
            ['patient_id'], ['__count'],
        )
        mapped_data = {patient.id: count for patient, count in data}
        for partner in self:
            partner.prescription_count = mapped_data.get(partner.id, 0)

    def _compute_policy_count(self):
        data = self.env['optical.policy']._read_group(
            [('patient_id', 'in', self.ids)],
            ['patient_id'], ['__count'],
        )
        mapped_data = {patient.id: count for patient, count in data}
        for partner in self:
            partner.policy_count = mapped_data.get(partner.id, 0)

    def _compute_subscriber_policy_count(self):
        data = self.env['optical.policy']._read_group(
            [('subscriber_id', 'in', self.ids)],
            ['subscriber_id'], ['__count'],
        )
        mapped_data = {subscriber.id: count for subscriber, count in data}
        for partner in self:
            partner.subscriber_policy_count = mapped_data.get(partner.id, 0)

    # --- Dossier patient : Actions smart buttons ---
    def action_view_prescriptions(self):
        """Ouvre la liste des ordonnances du patient."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Ordonnances de %s", self.name),
            'res_model': 'optical.prescription',
            'view_mode': 'list,form',
            'domain': [('patient_id', '=', self.id)],
            'context': {'default_patient_id': self.id},
        }

    def action_view_policies(self):
        """Ouvre la liste des polices du patient."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Polices de %s", self.name),
            'res_model': 'optical.policy',
            'view_mode': 'list,form',
            'domain': [('patient_id', '=', self.id)],
            'context': {'default_patient_id': self.id},
        }

    def action_view_subscriber_policies(self):
        """Ouvre la liste des polices souscrites par ce partenaire."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Polices souscrites par %s", self.name),
            'res_model': 'optical.policy',
            'view_mode': 'list,form',
            'domain': [('subscriber_id', '=', self.id)],
            'context': {'default_subscriber_id': self.id},
        }
