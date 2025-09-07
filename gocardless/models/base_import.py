# -*- coding: utf-8 -*-

from odoo import models
import datetime
import logging

_logger = logging.getLogger(__name__)


class GC_Importer(models.TransientModel):
    _inherit = 'base_import.import'

    def execute_import(self, fields, columns, options, dryrun=False):
        # Capturer l'heure exacte avant l'import pour identifier les nouveaux mandats
        import_start_time = datetime.datetime.now()
        
        # Récupérer les mandats existants avant l'import
        existing_mandates_before = self.env['gocardless.mandate'].sudo().search([]) if not dryrun else []
        existing_mandate_ids_before = set(existing_mandates_before.mapped('gc_mandate_id'))
        
        res_import = super(GC_Importer, self).execute_import(fields, columns, options, dryrun)

        # if we're in a dryrun then don't do anything
        if dryrun:
            return res_import

        # we only want to override for gocardless.mandate models
        if self.res_model == 'gocardless.mandate':
            # Identifier les mandats créés pendant l'import (nouveaux)
            new_mandates = self.env['gocardless.mandate'].sudo().search([
                ('create_date', '>=', import_start_time)
            ])
            
            duplicates_to_remove = []
            
            for mandate in new_mandates:
                if mandate.gc_mandate_id and mandate.gc_mandate_id in existing_mandate_ids_before:
                    # Ce mandat est un nouveau doublon (créé pendant l'import mais avec un ID existant)
                    duplicates_to_remove.append(mandate.id)
            
            # Supprimer les NOUVEAUX mandats en double (ceux qui viennent d'être importés)
            if duplicates_to_remove:
                self.env['gocardless.mandate'].sudo().browse(duplicates_to_remove).unlink()
                # Logger l'information
                _logger.info("%s mandat(s) nouvellement importés supprimés car leur Mandate ID existait déjà.", len(duplicates_to_remove))

            # Procéder au matching des partenaires comme avant
            for mandate in self.env['gocardless.mandate'].sudo().search(
                    ['&', ('partner_id', '=?', False), ('partner_email', '!=', '')]):
                partner = self.env['res.partner'].sudo().search(
                    ['&', ('mandate_id', '=', False), ('email', '=', mandate.partner_email)], limit=1)
                if partner:
                    mandate.write({'partner_id': partner.id, 'gc_last_state_change': datetime.date.today()})
                    partner.write({'gc_state': 'complete', 'mandate_id': mandate.id})

        return res_import
