# -*- coding: utf-8 -*-
"""Story 17-2 AC-5.3 — Wizard d'assignation en masse d'un référent.

Utilisé depuis la vue « Clients sans référent » : un manager sélectionne
1 à N partenaires sans commercial (``user_id=False`` ET
``optical_referent_user_id=False``) et leur assigne un référent en un clic.

Wizard 1 champ (``target_user_id`` required). Chatter par partner impacté.
Manager uniquement (ACL + garde-fou Python).
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class OpticalFollowupAssignReferentWizard(models.TransientModel):
    _name = 'optical.followup.assign.referent.wizard'
    _description = "Assigner un référent en masse à des clients sans référent"

    target_user_id = fields.Many2one(
        'res.users',
        string="Référent cible",
        required=True,
        help="Commercial à assigner comme référent sur les partenaires "
             "sélectionnés (champ res.partner.user_id).",
    )
    partner_ids = fields.Many2many(
        'res.partner',
        'optical_followup_assign_referent_wizard_partner_rel',
        'wizard_id',
        'partner_id',
        string="Partenaires à réassigner",
        help="Résolu depuis le context active_ids à l'ouverture du wizard.",
    )
    partner_count = fields.Integer(
        string="Nombre de partenaires",
        compute='_compute_partner_count',
        store=False,
    )

    @api.depends('partner_ids')
    def _compute_partner_count(self):
        for wizard in self:
            wizard.partner_count = len(wizard.partner_ids)

    @api.constrains('target_user_id')
    def _check_target_user_valid(self):
        """Revue M6 S17-2 — refuser user inactif ou hors périmètre optical.

        Un manager pourrait accidentellement sélectionner un user système,
        désactivé, ou hors du groupe commercial. Défense en profondeur.
        """
        group_user_id = self.env.ref(
            'optical.group_optical_user', raise_if_not_found=False,
        )
        group_manager_id = self.env.ref(
            'optical.group_optical_manager', raise_if_not_found=False,
        )
        allowed_users = self.env['res.users']
        if group_user_id:
            allowed_users |= group_user_id.users
        if group_manager_id:
            allowed_users |= group_manager_id.users
        for wizard in self:
            target = wizard.target_user_id
            if not target:
                continue
            if not target.active:
                raise ValidationError(_(
                    "Le référent cible %(name)s est désactivé — "
                    "impossible de lui assigner un portefeuille.",
                    name=target.name,
                ))
            if allowed_users and target not in allowed_users:
                raise ValidationError(_(
                    "Le référent cible %(name)s n'appartient pas au périmètre "
                    "optical (groupes Vendeur ou Responsable requis).",
                    name=target.name,
                ))

    @api.model
    def default_get(self, fields_list):
        """Charge les partners depuis le context ``active_ids`` (action de masse)."""
        vals = super().default_get(fields_list)
        active_model = self.env.context.get('active_model')
        active_ids = self.env.context.get('active_ids') or []
        if active_model == 'res.partner' and active_ids:
            vals['partner_ids'] = [(6, 0, active_ids)]
        return vals

    def _check_manager_or_raise(self):
        if not self.env.user.has_group('optical.group_optical_manager'):
            raise AccessError(_(
                "Seul un responsable peut assigner un référent en masse."
            ))

    def action_apply(self):
        """Story 17-2 AC-5.3 — écrit user_id sur chaque partner + chatter.

        Idempotence : un partner déjà assigné au ``target_user_id`` reçoit
        quand même un chatter (traçabilité — le manager confirme
        explicitement l'assignation, ce n'est pas un no-op silencieux).

        Après le write, les partners disparaissent de la vue « Clients sans
        référent » (recompute ``optical_referent_user_id``).
        """
        self._check_manager_or_raise()
        self.ensure_one()
        if not self.partner_ids:
            raise UserError(_(
                "Aucun partenaire sélectionné pour l'assignation."
            ))
        target = self.target_user_id
        partners = self.partner_ids
        # Revue M2 S17-2 — 1 UPDATE SQL batch au lieu de N updates séquentiels
        partners.sudo().write({'user_id': target.id})
        n_assigned = len(partners)
        # Chatter reste par-partner (mail.thread ne batch pas message_post)
        chatter_body = _(
            "Référent assigné à %(user)s par %(manager)s "
            "(action de masse).",
            user=target.name,
            manager=self.env.user.name,
        )
        for partner in partners:
            try:
                partner.message_post(
                    body=chatter_body,
                    subtype_xmlid='mail.mt_note',
                )
            except Exception as exc:  # noqa: BLE001 — chatter non critique
                _logger.exception(
                    "Assign référent wizard — chatter partner %s ignoré (%s).",
                    partner.id, exc,
                )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Référents assignés"),
                'message': _(
                    "%(n)s partenaire(s) réassigné(s) à %(user)s.",
                    n=n_assigned,
                    user=target.name,
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
