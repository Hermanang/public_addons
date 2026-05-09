# -*- coding: utf-8 -*-
from odoo import fields, models


class HelpdeskTicketStage(models.Model):
    _inherit = 'helpdesk.ticket.stage'

    validate_type_ids = fields.Many2many(
        comodel_name='helpdesk.ticket.type',
        relation='helpdesk_ticket_stage_validate_type_rel',
        column1='stage_id',
        column2='type_id',
        string="Types concernés par la validation",
        help="Si rempli, la validation des champs (configurée ci-dessus) "
             "ne s'applique qu'aux tickets de ces types. "
             "Si vide : la validation s'applique à tous les types.",
    )
