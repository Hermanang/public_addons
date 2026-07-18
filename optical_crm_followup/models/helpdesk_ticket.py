# -*- coding: utf-8 -*-
"""Extension ``helpdesk.ticket`` — Story 16.2 (suspension SAV).

Flux :

    create(vals_list)                       write(vals) [partner_id OR stage_id]
        │                                        │
        └─► sync partners_new                    └─► snapshot {partner, closed} AVANT super()
             (reopened_ticket=None)                  détecte closed→open (vraie réouverture)
                                                    sync partners_before ∪ partners_after
                                                        │
                                                        ▼
                            optical.followup.schedule._sync_sav_state_for_partner
                                        │
                                        ├─ tickets ouverts + running → pause + chatter
                                        ├─ tickets ouverts + reopened_ticket → chatter rouvert
                                        ├─ aucun ticket ouvert + paused SAV → reprise + chatter
                                        └─ autre → no-op

    unlink(self)
        └─► snapshot partners AVANT super() → sync après suppression
             (permet la reprise si le dernier ticket ouvert est supprimé)

Le chatter « rouvert » est réservé aux transitions **closed→open** détectées
par le hook write (via ``was_closed``) — jamais posté sur création d'un
nouveau ticket ni sur un write neutre de ``stage_id`` (idempotence AC10).

Le champ discriminant est ``stage_id.closed`` (Boolean) du module
``helpdesk_mgmt`` OCA — PAS ``stage.state='done'`` du module Enterprise.
"""
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'

    @api.model_create_multi
    def create(self, vals_list):
        tickets = super().create(vals_list)
        # Un ticket créé n'est jamais une "réouverture" — reopened_ticket=None.
        for partner in tickets.mapped('partner_id'):
            source = tickets.filtered(lambda t: t.partner_id == partner)[:1]
            self._optical_sync_sav_for_partner(
                partner, source_ticket=source, reopened_ticket=None,
            )
        return tickets

    def write(self, vals):
        # Snapshot AVANT super() : partner + closed par ticket, pour :
        #   1. capturer les partners délestés lors d'un changement partner_id
        #   2. détecter les transitions closed=True → False (vraie réouverture)
        snapshot = {
            t.id: {'partner': t.partner_id, 'was_closed': t.closed}
            for t in self
        }

        result = super().write(vals)

        # Sync uniquement si un champ discriminant a changé.
        if 'partner_id' not in vals and 'stage_id' not in vals:
            return result

        # Réouvertures explicites : ticket dont closed=True AVANT et False APRÈS.
        # Indexé par partner_id (courant) pour associer chaque partner à
        # UN ticket rouvert au plus (le premier détecté).
        reopened_by_partner = {}
        for ticket in self:
            prev = snapshot.get(ticket.id, {})
            if prev.get('was_closed') and not ticket.closed and ticket.partner_id:
                reopened_by_partner.setdefault(ticket.partner_id.id, ticket)

        partners_to_sync = self.env['res.partner']
        for ticket in self:
            partners_to_sync |= ticket.partner_id
            before = snapshot.get(ticket.id, {}).get('partner')
            if before:
                partners_to_sync |= before
        for partner in partners_to_sync:
            if not partner:
                continue
            # Ticket source : préférer un ticket de self dont le partner
            # courant matche ; sinon fallback sur self[:1].
            source = self.filtered(lambda t: t.partner_id == partner)[:1] or self[:1]
            reopened = reopened_by_partner.get(partner.id)
            self._optical_sync_sav_for_partner(
                partner, source_ticket=source, reopened_ticket=reopened,
            )
        return result

    def unlink(self):
        # Snapshot des partners AVANT unlink — le sync ne s'applique qu'aux
        # partners qui perdent un ticket (potentiellement leur dernier ouvert
        # → schedule doit reprendre).
        partners_before = {t.partner_id for t in self if t.partner_id}
        result = super().unlink()
        for partner in partners_before:
            self._optical_sync_sav_for_partner(
                partner, source_ticket=None, reopened_ticket=None,
            )
        return result

    @api.model
    def _optical_sync_sav_for_partner(self, partner, source_ticket=None, reopened_ticket=None):
        """Délègue à ``optical.followup.schedule._sync_sav_state_for_partner``.

        Isolé pour testabilité (mockable). Le hook helpdesk ne doit jamais
        casser la transaction — toute exception est journalisée sans être
        propagée (AC2 rétro 15).

        ``reopened_ticket`` : ticket dont la transition closed=True→False a
        été détectée par le hook write. ``None`` en création, unlink, ou
        write sans réouverture réelle.
        """
        if not partner:
            return
        try:
            self.env['optical.followup.schedule']._sync_sav_state_for_partner(
                partner,
                source_ticket=source_ticket,
                reopened_ticket=reopened_ticket,
            )
        except Exception as exc:  # noqa: BLE001 — résilience hook
            _logger.exception(
                "Sync SAV followup — partner %s ignoré (%s).",
                partner.id, exc,
            )
