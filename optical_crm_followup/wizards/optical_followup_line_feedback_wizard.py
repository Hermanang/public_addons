# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class OpticalFollowupLineFeedbackWizard(models.TransientModel):
    _name = 'optical.followup.line.feedback.wizard'
    _description = "Wizard clôture d'une étape de suivi (outcome)"

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
