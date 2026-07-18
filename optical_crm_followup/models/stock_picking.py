# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        """Hook Story 15.2 : à la validation d'un picking outgoing, tente la
        création d'un calendrier de suivi (fidélisation).

        On appelle ``super()`` en premier pour que ``picking.state`` soit
        ``done`` et que ``date_done`` soit renseigné avant la logique de
        création. La création est faite en ``sudo()`` (les commerciaux n'ont
        pas les droits C sur le schedule — cf. matrice ACL 15.0).
        """
        result = super()._action_done()
        self._optical_trigger_followup()
        return result

    def _optical_trigger_followup(self):
        """Itère les pickings outgoing validés et tente la création du calendrier."""
        Schedule = self.env['optical.followup.schedule']
        for picking in self:
            if picking.picking_type_id.code != 'outgoing':
                continue
            if picking.state != 'done':
                continue
            if not picking.sale_id:
                continue
            # On isole la création dans un savepoint pour que l'échec sur un
            # picking n'annule pas la remise (validation) et ne pollue pas les
            # pickings suivants du batch (cf. code review S15.2 H3/H4).
            try:
                with self.env.cr.savepoint():
                    Schedule._create_from_picking(picking)
            except Exception as exc:  # noqa: BLE001 — on ne veut pas casser la remise
                # `.error` (et non `.exception`) pour maximiser la visibilité
                # dans les stacks d'observabilité — le traceback est joint.
                _logger.error(
                    "Erreur création calendrier followup pour picking %s : %s",
                    picking.name, exc, exc_info=True,
                )
