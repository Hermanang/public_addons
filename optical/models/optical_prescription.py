# -*- coding: utf-8 -*-
import logging

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class OpticalPrescription(models.Model):
    _name = 'optical.prescription'
    _description = "Ordonnance optique"
    _inherit = ['mail.thread.main.attachment', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    # --- Champs relationnels et metadonnées ---
    name = fields.Char(
        string="Reference",
        readonly=True,
        default=lambda self: _('Nouveau'),
        copy=False,
        index='trigram',
    )
    patient_id = fields.Many2one(
        'res.partner',
        string="Patient",
        required=True,
        domain="[('is_patient', '=', True)]",
        tracking=True,
        index='btree_not_null',
        ondelete='restrict',
    )
    prescriber_id = fields.Many2one(
        'res.partner',
        string="Prescripteur",
        required=True,
        domain="[('is_prescriber', '=', True)]",
        tracking=True,
        index='btree_not_null',
        ondelete='restrict',
    )
    date = fields.Date(
        string="Date de prescription",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    date_expiry = fields.Date(
        string="Date d'expiration",
        compute='_compute_date_expiry',
        store=True,
        precompute=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ('draft', "Brouillon"),
            ('confirmed', "Confirmé"),
            ('expired', "Expiré"),
        ],
        string="État",
        default='draft',
        required=True,
        tracking=True,
        index=True,
        copy=False,
    )
    notes = fields.Text(string="Observations")
    company_id = fields.Many2one(
        'res.company',
        string="Societe",
        required=True,
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(default=True)

    # --- Champs metier complementaires (CC-2026-03-07-PRESCRIPTION-UX) ---
    vision_type = fields.Selection(
        [('far', "Vision de loin"), ('near', "Vision de près"),
         ('intermediate', "Vision intermédiaire"), ('progressive', "Progressif")],
        string="Type de vision",
    )
    measure_type = fields.Selection(
        [('glasses', "Verres"), ('contact_lenses', "Lentilles")],
        string="Type de prescription",
    )
    measure_date = fields.Date(string="Date de la mesure")

    # --- Mesures OD (oeil droit) ---
    od_sphere = fields.Float(
        string="SPH OD",
        digits=(4, 2),
        help="Sphere oeil droit (-20.00 a +20.00 dioptries)",
    )
    od_cylinder = fields.Float(
        string="CYL OD",
        digits=(4, 2),
        help="Cylindre oeil droit (0.00 a -8.00 dioptries)",
    )
    od_axis = fields.Integer(
        string="AXE OD",
        help="Axe oeil droit (0 a 180 degres)",
    )
    od_addition = fields.Float(
        string="ADD OD",
        digits=(3, 2),
        help="Addition oeil droit (0.00 a +4.00 dioptries)",
    )
    od_prism = fields.Float(
        string="Prisme OD",
        digits=(3, 2),
        help="Prisme oeil droit",
    )
    od_prism_base = fields.Selection(
        [
            ('up', "Haut"),
            ('down', "Bas"),
            ('in', "Interne"),
            ('out', "Externe"),
        ],
        string="Base prisme OD",
    )
    od_pd = fields.Float(
        string="EP OD",
        digits=(3, 1),
        help="Ecart pupillaire oeil droit (mm)",
    )

    # --- Mesures OG (oeil gauche) ---
    og_sphere = fields.Float(
        string="SPH OG",
        digits=(4, 2),
        help="Sphere oeil gauche (-20.00 a +20.00 dioptries)",
    )
    og_cylinder = fields.Float(
        string="CYL OG",
        digits=(4, 2),
        help="Cylindre oeil gauche (0.00 a -8.00 dioptries)",
    )
    og_axis = fields.Integer(
        string="AXE OG",
        help="Axe oeil gauche (0 a 180 degres)",
    )
    og_addition = fields.Float(
        string="ADD OG",
        digits=(3, 2),
        help="Addition oeil gauche (0.00 a +4.00 dioptries)",
    )
    og_prism = fields.Float(
        string="Prisme OG",
        digits=(3, 2),
        help="Prisme oeil gauche",
    )
    og_prism_base = fields.Selection(
        [
            ('up', "Haut"),
            ('down', "Bas"),
            ('in', "Interne"),
            ('out', "Externe"),
        ],
        string="Base prisme OG",
    )
    og_pd = fields.Float(
        string="EP OG",
        digits=(3, 1),
        help="Ecart pupillaire oeil gauche (mm)",
    )

    # --- EP binoculaire ---
    pd_total = fields.Float(
        string="EP Total",
        digits=(3, 1),
        help="Ecart pupillaire total (mm)",
    )

    # --- Computed ---
    @api.depends('date', 'patient_id.birthdate')
    def _compute_date_expiry(self):
        for rec in self:
            if rec.date:
                expiry_years = 3  # Defaut adulte (FR10)
                if rec.patient_id.birthdate:
                    age_at_prescription = relativedelta(rec.date, rec.patient_id.birthdate).years
                    if age_at_prescription < 16:
                        expiry_years = 1  # Mineur (FR59)
                rec.date_expiry = rec.date + relativedelta(years=expiry_years)
            else:
                rec.date_expiry = False

    # --- Contraintes ---
    @api.constrains(
        'od_sphere', 'og_sphere',
        'od_cylinder', 'og_cylinder',
        'od_axis', 'og_axis',
        'od_addition', 'og_addition',
        'od_prism', 'og_prism',
    )
    def _check_optical_measures(self):
        step_fields = {'sphere', 'cylinder', 'addition'}
        for rec in self:
            for eye, label in [('od', 'OD'), ('og', 'OG')]:
                sphere = getattr(rec, f'{eye}_sphere')
                if sphere and abs(sphere) > 20:
                    raise ValidationError(
                        _("%(label)s Sphere : la valeur %(value)s est hors plage (-20.00 a +20.00 dioptries).",
                          label=label, value=sphere)
                    )
                cylinder = getattr(rec, f'{eye}_cylinder')
                if cylinder and (cylinder > 0 or cylinder < -8):
                    raise ValidationError(
                        _("%(label)s Cylindre : la valeur %(value)s est hors plage (0.00 a -8.00 dioptries).",
                          label=label, value=cylinder)
                    )
                axis = getattr(rec, f'{eye}_axis')
                if axis and (axis < 0 or axis > 180):
                    raise ValidationError(
                        _("%(label)s Axe : la valeur %(value)s est hors plage (0 a 180 degres).",
                          label=label, value=axis)
                    )
                addition = getattr(rec, f'{eye}_addition')
                if addition and (addition < 0 or addition > 4):
                    raise ValidationError(
                        _("%(label)s Addition : la valeur %(value)s est hors plage (0.00 a +4.00 dioptries).",
                          label=label, value=addition)
                    )
                # Validation step 0,25 pour sphere, cylindre, addition (FR60)
                for field_name in step_fields:
                    value = getattr(rec, f'{eye}_{field_name}')
                    if value and abs((value * 4) - round(value * 4)) > 1e-9:
                        field_label = {'sphere': 'Sphere', 'cylinder': 'Cylindre', 'addition': 'Addition'}[field_name]
                        raise ValidationError(
                            _("%(label)s %(field)s : la valeur %(value)s doit etre un multiple de 0,25 dioptries.",
                              label=label, field=field_label, value=value)
                        )

    # --- Helpers ---
    def format_diopter(self, value, decimals=2):
        """Formate une valeur dioptrie pour affichage : +1,25 / -0,50 / 0,00
        Retourne '' si value est None ou False (champ vide).
        """
        if value is None or value is False:
            return ""
        if not value:
            return "0," + "0" * decimals
        return f"{value:+.{decimals}f}".replace('.', ',')

    # --- Actions ---
    def action_confirm(self):
        self.ensure_one()
        if not self.patient_id:
            raise UserError(_("Un patient doit etre selectionne pour confirmer l'ordonnance."))
        if not self.prescriber_id:
            raise UserError(_("Un prescripteur doit etre selectionne pour confirmer l'ordonnance."))
        self.state = 'confirmed'

    def action_reset_to_draft(self):
        self.ensure_one()
        if self.state == 'expired':
            raise UserError(_("Une ordonnance expiree ne peut pas etre remise en brouillon."))
        self.state = 'draft'

    # --- Cron ---
    def _cron_expire_prescriptions(self):
        """Cron : expire les ordonnances confirmées dont la date d'expiration est depassee (FR12)."""
        today = fields.Date.context_today(self)
        expired = self.search([
            ('state', '=', 'confirmed'),
            ('date_expiry', '<', today),
        ])
        if expired:
            expired.write({'state': 'expired'})
            _logger.info(
                "Cron expiration ordonnances : %d ordonnance(s) expiree(s).",
                len(expired),
            )

    # --- CRUD overrides ---
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('Nouveau'):
                vals['name'] = self.env['ir.sequence'].next_by_code('optical.prescription')
        return super().create(vals_list)

    def unlink(self):
        raise UserError(_("La suppression n'est pas autorisee. Utilisez l'archivage."))
