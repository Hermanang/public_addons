# -*- coding: utf-8 -*-
import logging
import re
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

_CIVIL_DATE_RE = re.compile(r'^\d{2}-\d{2}$')


class OpticalFollowupHolidayWindow(models.Model):
    _name = 'optical.followup.holiday.window'
    _description = "Fenêtre de vigilance saisonnière"
    _order = 'sequence, id'

    name = fields.Char(string="Nom", required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    lunar_date_id = fields.Many2one(
        'optical.followup.lunar.date',
        string="Ancrage lunaire",
        ondelete='restrict',
        help="Ancrage sémantique pour les fenêtres lunaires. La résolution "
             "année-glissante se fait via `event` + année cible (voir "
             "`_get_effective_period`). Vide pour les fenêtres civiles. "
             "`ondelete='restrict'` protège contre une suppression accidentelle "
             "qui laisserait la fenêtre sans ancrage valide.",
    )
    date_start_civil = fields.Char(
        string="Début (civil MM-DD)",
        help="Date de début au format `MM-DD` (mois-jour, année-glissante). "
             "Exemple : `12-23`. Vide pour les fenêtres lunaires.",
    )
    date_end_civil = fields.Char(
        string="Fin (civil MM-DD)",
        help="Date de fin au format `MM-DD` (mois-jour, année-glissante). "
             "Exemple : `01-03`. Vide pour les fenêtres lunaires.",
    )
    duration_days = fields.Integer(
        string="Durée (jours)",
        default=0,
        help="Durée utilisée pour les fenêtres lunaires quand la lunaire "
             "cible n'a pas de date de fin renseignée.",
    )
    behavior = fields.Selection(
        [
            ('postpone_to_end', "Reporter à la fin de la fenêtre"),
            ('switch_channel_soft', "Basculer sur canal doux (indicatif)"),
            ('none', "Aucun (fenêtre neutre)"),
        ],
        string="Comportement",
        default='none',
        required=True,
        help="Action appliquée à la matérialisation d'une activité tombant "
             "dans cette fenêtre.",
    )
    suggested_channel = fields.Selection(
        [
            ('email', "Email"),
            ('whatsapp', "WhatsApp"),
            ('call', "Appel téléphonique"),
            ('in_person', "Visite en boutique"),
        ],
        string="Canal recommandé",
        help="Utilisé pour `switch_channel_soft` : ajoute une mention dans "
             "la note d'activité pour suggérer ce canal.",
    )
    description = fields.Text(
        string="Description",
        help="Contexte de la fenêtre (informationnel, éditable post-install).",
    )

    # ------------------------------------------------------------------
    # Contraintes
    # ------------------------------------------------------------------

    @api.constrains('date_start_civil', 'date_end_civil')
    def _check_civil_dates_format(self):
        for window in self:
            start, end = window.date_start_civil, window.date_end_civil
            for label, value in (('début', start), ('fin', end)):
                if not value:
                    continue
                if not _CIVIL_DATE_RE.match(value):
                    raise ValidationError(_(
                        "Fenêtre « %(name)s » : date civile de %(label)s "
                        "invalide (%(value)r). Format attendu : `MM-DD`.",
                        name=window.name, label=label, value=value,
                    ))
                month, day = (int(x) for x in value.split('-'))
                # Année bisextile arbitraire (2000) pour tolérer 02-29.
                try:
                    date(2000, month, day)
                except ValueError:
                    raise ValidationError(_(
                        "Fenêtre « %(name)s » : date civile de %(label)s "
                        "invalide (%(value)r). Mois attendu 01-12, jour "
                        "cohérent avec le mois.",
                        name=window.name, label=label, value=value,
                    ))
            if bool(start) != bool(end):
                raise ValidationError(_(
                    "Fenêtre « %(name)s » : les dates civiles de début et "
                    "de fin doivent être toutes deux renseignées ou toutes "
                    "deux vides.",
                    name=window.name,
                ))

    @api.constrains('lunar_date_id', 'date_start_civil')
    def _check_at_least_one_source(self):
        for window in self:
            if not window.lunar_date_id and not window.date_start_civil:
                raise ValidationError(_(
                    "Fenêtre « %(name)s » : renseigner soit un ancrage "
                    "lunaire, soit une plage civile (`MM-DD`) — sinon la "
                    "fenêtre est inapplicable.",
                    name=window.name,
                ))

    # ------------------------------------------------------------------
    # Résolution année-glissante (AC5)
    # ------------------------------------------------------------------

    def _get_effective_period(self, year):
        """Retourne le tuple ``(date_start, date_end)`` pour l'année ``year``.

        - Fenêtre lunaire : recherche la ``optical.followup.lunar.date``
          d'événement ``lunar_date_id.event`` et d'année ``year``. Retourne
          ``(False, False)`` si absente (log warning). Si la lunaire n'a
          pas de ``date_gregorian_end``, calcule ``start + duration_days - 1``.
        - Fenêtre civile : construit ``date(year, month, day)`` depuis
          ``date_start_civil`` / ``date_end_civil``. Gère le franchissement
          d'année (fin.month < start.month → +1 an sur la fin).
        """
        self.ensure_one()

        if self.lunar_date_id:
            event = self.lunar_date_id.event
            lunar = self.env['optical.followup.lunar.date'].sudo().search(
                [('event', '=', event), ('year', '=', year)],
                limit=1,
            )
            if not lunar:
                # `debug` : le cron itère sur toutes les fenêtres actives à
                # chaque matérialisation ; une année lunaire manquante n'est
                # pas anormale en soi (rétro 15 § 6.6 R2 documente l'audit
                # annuel de maintenance). Un warning quotidien saturait les
                # logs — on préserve la traçabilité en debug.
                _logger.debug(
                    "Fenêtre %s : table lunaire indisponible pour année "
                    "%s (event=%s).",
                    self.name, year, event,
                )
                return (False, False)
            date_start = lunar.date_gregorian_start
            date_end = lunar.date_gregorian_end
            if not date_end and self.duration_days:
                date_end = fields.Date.add(
                    date_start, days=self.duration_days - 1,
                )
            elif not date_end:
                date_end = date_start
            return (date_start, date_end)

        if self.date_start_civil and self.date_end_civil:
            start_m, start_d = (int(x) for x in self.date_start_civil.split('-'))
            end_m, end_d = (int(x) for x in self.date_end_civil.split('-'))
            try:
                date_start = date(year, start_m, start_d)
                end_year = year + 1 if end_m < start_m else year
                date_end = date(end_year, end_m, end_d)
            except ValueError as exc:
                _logger.warning(
                    "Fenêtre %s : dates civiles invalides pour année %s "
                    "(%s).", self.name, year, exc,
                )
                return (False, False)
            return (date_start, date_end)

        return (False, False)

    @api.model
    def _find_applicable(self, target_date):
        """Cherche parmi les fenêtres actives celle applicable à ``target_date``.

        Règle de priorité (AC9) :
          1. Fenêtres actives filtrées puis triées par ``sequence, id``.
          2. Pour chaque fenêtre, calcul de la période effective à
             l'année de ``target_date``. Pour les fenêtres civiles qui
             franchissent l'année (ex. `12-23` → `01-03`), on essaie aussi
             l'année N-1 pour capturer les dates de janvier.
          3. Retenir la 1ʳᵉ fenêtre matchée dont le comportement est
             ``postpone_to_end`` ; à défaut la 1ʳᵉ ``switch_channel_soft`` ;
             à défaut la 1ʳᵉ ``none``.
          4. Si plusieurs fenêtres matchent, log info listant les fenêtres
             ignorées.

        Retourne ``(window, date_start, date_end)`` où ``window`` est un
        recordset unitaire et ``date_start/date_end`` la période effective
        résolue à l'année cible. Retourne ``None`` si aucune fenêtre ne
        s'applique — évite de recomputer la période côté caller (cf.
        `_apply_holiday_window`, cascade postpone).
        """
        windows = self.sudo().search(
            [('active', '=', True)], order='sequence, id',
        )
        matched = []  # liste de (window, start, end)
        year = target_date.year
        for window in windows:
            candidate_years = [year]
            # Fenêtre civile franchissant l'année : essayer aussi year-1 pour
            # capturer les dates de janvier (période démarrée en décembre).
            if (
                window.date_start_civil
                and window.date_end_civil
                and int(window.date_end_civil.split('-')[0])
                < int(window.date_start_civil.split('-')[0])
            ):
                candidate_years.insert(0, year - 1)
            for candidate_year in candidate_years:
                start, end = window._get_effective_period(candidate_year)
                if start and end and start <= target_date <= end:
                    matched.append((window, start, end))
                    break

        if not matched:
            return None

        by_behavior = {'postpone_to_end': [], 'switch_channel_soft': [], 'none': []}
        for entry in matched:
            by_behavior[entry[0].behavior].append(entry)

        winner = None
        for behavior in ('postpone_to_end', 'switch_channel_soft', 'none'):
            if by_behavior[behavior]:
                winner = by_behavior[behavior][0]
                break

        if not winner:
            return None

        ignored = [e for e in matched if e[0].id != winner[0].id]
        if ignored:
            _logger.info(
                "Fenêtres additionnelles ignorées pour %s (retenue : %s / %s) : %s",
                target_date, winner[0].name, winner[0].behavior,
                ', '.join('%s (%s)' % (e[0].name, e[0].behavior) for e in ignored),
            )
        return winner
