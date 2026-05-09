# -*- coding: utf-8 -*-
from odoo import models


class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'

    def _check_ticket_has_empty_fields(self):
        """Override : si le stage filtre par type, ignorer la validation
        pour les tickets dont le type n'est pas dans la liste filtrée.

        Pas de sudo() : helpdesk.ticket.stage est lisible par tout user
        helpdesk via les groupes natifs helpdesk_mgmt. Garder en clair
        pour respecter le principe de moindre privilège.
        """
        self.ensure_one()
        validate_types = self.stage_id.validate_type_ids
        if validate_types and self.type_id not in validate_types:
            return False
        return super()._check_ticket_has_empty_fields()
