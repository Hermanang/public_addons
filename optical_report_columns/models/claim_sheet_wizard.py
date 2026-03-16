# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class ClaimSheetWizardColumns(models.TransientModel):
    _inherit = 'optical.claim.sheet.wizard'

    report_column_ids = fields.Many2many(
        'report.dynamic.column',
        relation='claim_sheet_wizard_dynamic_column_rel',
        column1='wizard_id', column2='column_id',
        string='Colonnes du rapport',
        domain="[('report_type', '=', 'claim_sheet')]",
    )
    profile_id = fields.Many2one(
        'report.dynamic.column.profile',
        string='Profil de colonnes',
        domain="[('report_type', '=', 'claim_sheet')]",
    )
    has_profile = fields.Boolean(
        string='Profil actif',
        compute='_compute_has_profile',
    )

    @api.depends('profile_id')
    def _compute_has_profile(self):
        for wizard in self:
            wizard.has_profile = bool(wizard.profile_id)

    @api.onchange('insurer_id')
    def _onchange_insurer_columns(self):
        """Charge les colonnes : profil partner > profil défaut > flags type assureur."""
        if not self.insurer_id:
            self.report_column_ids = False
            self.profile_id = False
            return

        # 1. Chercher profil spécifique à cet assureur
        Profile = self.env['report.dynamic.column.profile']
        profile = Profile.search([
            ('report_type', '=', 'claim_sheet'),
            ('partner_id', '=', self.insurer_id.id),
        ], limit=1)

        # 2. Si pas de profil partner, chercher profil par défaut global
        if not profile:
            profile = Profile.search([
                ('report_type', '=', 'claim_sheet'),
                ('partner_id', '=', False),
                ('is_default', '=', True),
            ], limit=1)

        # 3. Si profil trouvé, charger ses colonnes
        if profile:
            self.profile_id = profile
            self.report_column_ids = profile.column_ids
            return

        # 4. Fallback : flags default_insurance/default_ipm (comportement existant)
        self.profile_id = False
        field_name = (
            'default_insurance' if self.insurer_id.insurer_type == 'insurance'
            else 'default_ipm'
        )
        columns = self.env['report.dynamic.column'].search([
            ('report_type', '=', 'claim_sheet'),
            (field_name, '=', True),
            ('active', '=', True),
        ], order='sequence, id')
        self.report_column_ids = columns

    def action_save_profile(self):
        """Crée ou met à jour un profil de colonnes pour l'assureur sélectionné."""
        self.ensure_one()
        if not self.insurer_id or not self.report_column_ids:
            raise UserError("Sélectionnez un assureur et des colonnes avant de sauvegarder.")
        Profile = self.env['report.dynamic.column.profile'].sudo()
        # Chercher un profil existant pour éviter les doublons
        existing = Profile.search([
            ('report_type', '=', 'claim_sheet'),
            ('partner_id', '=', self.insurer_id.id),
        ], limit=1)
        if existing:
            existing.column_ids = [fields.Command.set(self.report_column_ids.ids)]
            self.profile_id = existing
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Profil mis à jour',
                    'message': f'Profil "{existing.name}" mis à jour avec {len(self.report_column_ids)} colonnes.',
                    'type': 'success',
                    'sticky': False,
                },
            }
        profile = Profile.create({
            'name': self.insurer_id.name,
            'report_type': 'claim_sheet',
            'partner_id': self.insurer_id.id,
            'column_ids': [fields.Command.set(self.report_column_ids.ids)],
        })
        self.profile_id = profile
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Profil sauvegardé',
                'message': f'Profil "{profile.name}" créé avec {len(self.report_column_ids)} colonnes.',
                'type': 'success',
                'sticky': False,
            },
        }

    def action_update_profile(self):
        """Met à jour le profil existant avec les colonnes actuelles."""
        self.ensure_one()
        if not self.profile_id:
            raise UserError("Aucun profil à mettre à jour.")
        self.profile_id.sudo().column_ids = [fields.Command.set(self.report_column_ids.ids)]
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Profil mis à jour',
                'message': f'Profil "{self.profile_id.name}" mis à jour.',
                'type': 'success',
                'sticky': False,
            },
        }

    def action_generate(self):
        """Surcharge pour stocker les colonnes sur le bordereau généré."""
        self.ensure_one()
        # Déterminer les colonnes avant super() (qui génère le claim_sheet)
        columns = self.report_column_ids
        if not columns:
            columns = self.env['report.dynamic.column'].search([
                ('report_type', '=', 'claim_sheet'),
                ('active', '=', True),
            ], order='sequence, id')
        res = super().action_generate()
        # Récupérer le claim_sheet créé (pattern identique au bridge OU)
        claim_sheet = self.invoice_ids[:1].claim_sheet_id
        if claim_sheet:
            claim_sheet.write({'column_ids': [fields.Command.set(columns.ids)]})
        return res
