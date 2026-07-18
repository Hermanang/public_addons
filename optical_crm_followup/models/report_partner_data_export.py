# -*- coding: utf-8 -*-
"""Story 17-3 AC-D — AbstractModel garde-fou du rapport « Droit d'accès CDP ».

Un AbstractModel nommé ``report.<report_name>`` est appelé par le moteur QWeb
(via ``IrActionsReport._render_qweb_pdf → _get_rendering_context``) pour
fournir le contexte du template. C'est ici qu'on impose le garde-fou groupe
manager : sans lui, l'URL ``/report/pdf/<report_name>/<id>`` reste
publiquement accessible à tout utilisateur interne ayant droit de lire
``res.partner`` (revue adversarial S17-3 H2 — fuite PII).
"""
from odoo import _, api, models
from odoo.exceptions import AccessError


class ReportPartnerDataExport(models.AbstractModel):
    _name = 'report.optical_crm_followup.report_partner_data_export_document'
    _description = "Contexte QWeb + garde-fou droit d'accès CDP"

    @api.model
    def _get_report_values(self, docids, data=None):
        if not self.env.user.has_group('optical.group_optical_manager'):
            raise AccessError(_(
                "L'extrait droit d'accès (Loi 2008-12 art. 65-71) est réservé "
                "aux responsables — il contient des données personnelles "
                "sensibles."
            ))
        return {
            'doc_ids': docids,
            'doc_model': 'res.partner',
            'docs': self.env['res.partner'].browse(docids),
        }
