# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    delivered_date = fields.Date(
        string="Date de remise (fidélisation)",
        readonly=True,
        help="Renseignée automatiquement au moment de la validation du picking "
             "outgoing (dernière date_done).",
    )
    followup_schedule_id = fields.Many2one(
        'optical.followup.schedule',
        string="Calendrier de fidélisation",
        readonly=True,
        ondelete='set null',
        index=True,
        help="Pointeur vers le calendrier créé au picking outgoing. Alimente le "
             "smart-button d'accès rapide.",
    )
    followup_activated = fields.Boolean(
        string="Suivi activé",
        compute='_compute_followup_activated',
        store=True,
        help="True si un calendrier de fidélisation a été créé pour cette SO. "
             "Sert de dimension de ventilation à la vue pivot KPI 4 "
             "(taux d'activation du consentement — Story 17-2 AC-4).",
    )

    @api.depends('followup_schedule_id')
    def _compute_followup_activated(self):
        for order in self:
            order.followup_activated = bool(order.followup_schedule_id)
    picking_late_alert_sent = fields.Boolean(
        string="Alerte picking > 7 j envoyée",
        readonly=True,
        default=False,
        help="Anti-doublon pour la mitigation R1 (alerte manager en cas de "
             "picking outgoing bloqué plus de 7 jours).",
    )
    picking_late_alert_activity_id = fields.Many2one(
        'mail.activity',
        string="Activité alerte picking > 7 j",
        readonly=True,
        ondelete='set null',
        help="Pointeur direct vers l'activité warning créée par le cron. "
             "Permet une fermeture idempotente quand le picking est validé "
             "(pas de dépendance à un match sur summary traduit).",
    )

    def action_open_followup_schedule(self):
        """Smart-button vers le calendrier de fidélisation associé."""
        self.ensure_one()
        if not self.followup_schedule_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _("Calendrier de fidélisation"),
            'res_model': 'optical.followup.schedule',
            'res_id': self.followup_schedule_id.id,
            'view_mode': 'form',
        }
