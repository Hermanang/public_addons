# -*- coding: utf-8 -*-

from odoo import models
import logging

_logger = logging.getLogger(__name__)


class GC_Importer(models.TransientModel):
    _inherit = 'base_import.import'

    def execute_import(self, fields, columns, options, dryrun=False):
        res_import = super(GC_Importer, self).execute_import(fields, columns, options, dryrun)

        # if we're in a dryrun then don't do anything
        if dryrun:
            return res_import

        # we only want to override for gocardless.mandate models
        if self.res_model == 'gocardless.mandate':
            # it's go time!
            for m in self.env['gocardless.mandate'].sudo().search(
                    ['&', ('partner_id', '=?', False), ('partner_email', '!=', '')]):
                #                try:
                p = self.env['res.partner'].sudo().search(
                    ['&', ('mandate_id', '=', False), ('email', '=', m.partner_email)], limit=1)
                _logger.debug("Matched mandate {} to {}".format(m.gc_mandate_id, p.name))
                m.write({
                    'partner_id': p.id,
                    # 'gc_last_state_change': datetime.date.today()
                })
                p.write({
                    'gc_state': 'complete',
                    'mandate_id': m.id
                })
        #                except:
        #                    continue
        # rof
        # endif
        return res_import
