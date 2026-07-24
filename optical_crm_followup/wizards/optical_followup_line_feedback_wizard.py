# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class OpticalFollowupLineFeedbackWizard(models.TransientModel):
    _name = 'optical.followup.line.feedback.wizard'
    _description = "Wizard clôture d'une étape de suivi (outcome)"

    @api.model
    def default_get(self, fields_list):
        """Pré-remplit ``line_id`` depuis l'étape sélectionnée.

        L'action contextuelle « Clôturer l'étape » (binding sur
        ``optical.followup.schedule.line``) transmet l'étape via
        ``active_id`` ; sans ce default_get le wizard s'ouvrait vide et
        ``action_confirm`` échouait (« Aucune étape à clôturer »).
        """
        res = super().default_get(fields_list)
        if not res.get('line_id') and self.env.context.get(
            'active_model'
        ) == 'optical.followup.schedule.line':
            active_id = self.env.context.get('active_id')
            if active_id:
                res['line_id'] = active_id
        return res

    line_id = fields.Many2one(
        'optical.followup.schedule.line',
        string="Étape de suivi",
        required=True,
    )
    partner_id = fields.Many2one(
        related='line_id.schedule_id.partner_id',
        readonly=True,
    )
    step_name = fields.Char(related='line_id.step_id.name', readonly=True)
    outcome = fields.Selection(
        [
            ('answered', "Répondu"),
            ('unreachable', "Injoignable"),
            ('refused', "Refusé poliment"),
            ('purchased', "A acheté"),
        ],
        string="Issue du contact",
        required=True,
    )
    note = fields.Text(string="Commentaire (optionnel)")

    def action_confirm(self):
        self.ensure_one()
        if not self.line_id:
            raise UserError(_("Aucune étape à clôturer."))
        self.line_id._mark_done(self.outcome, note=self.note)
        return {'type': 'ir.actions.act_window_close'}
