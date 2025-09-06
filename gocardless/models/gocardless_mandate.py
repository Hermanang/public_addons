# -*- coding: utf-8 -*-

from odoo import models, fields
import logging
import datetime

_logger = logging.getLogger(__name__)


class GC_Mandate(models.Model):
    _name = 'gocardless.mandate'
    _description = 'GoCardless Mandate'
    _check_company_auto = True

    _rec_name = 'gc_mandate_id'

    config_id = fields.Many2one(
        'gocardless.config',
        string='Configuration',
        required=True,
        default=lambda self: self.env['gocardless.config'].get_default_config(),
        ondelete='restrict',
        help="GoCardless configuration this mandate belongs to"
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='config_id.company_id',
        store=True,
        readonly=True,
        index=True
    )

    gc_state = fields.Selection(
        [
            ['pending', 'Pending'],
            ['created', 'Created'],
            ['pending_submission', 'Pending Submission'],
            ['submitted', 'Submitted'],
            ['active', 'Active'],
            ['reinstated', 'Reinstated'],
            ['cancelled', 'Cancelled'],
            ['failed', 'Failed'],
            ['consumed', 'Consumed'],
            ['blocked', 'Blocked'],
            ['suspended_by_payer', 'Suspended by payer'],
            ['expired', 'Expired'],
            ['resubmission_requested', 'Resubmission requested'],
            ['replaced', 'Replaced'],
            ['pending_customer_approval', 'Pending customer approval'],
            ['customer_approval_granted', 'Customer approval granted'],
            ['customer_approval_skipped', 'Customer approval skipped']
        ],
        string="Mandate state:",
        required=True
    )

    gc_last_state_change = fields.Date("Last updated",
                                       default=datetime.date(year=1970, month=1, day=1)
                                       )

    gc_mandate_id = fields.Char("GoCardless Mandate ID", required=True)
    event_ids = fields.One2many(comodel_name='gocardless.event', inverse_name='mandate_id', string="Events")
    partner_id = fields.Many2one(comodel_name='res.partner', string='Partner')
    partner_email = fields.Char(string='Email', related='partner_id.email', store=True, readonly=False)

    def mandateUpdate(self):
        # Method no longer used - keeping its stub to avoid
        # unnecessary cron exceptions
        _logger.warning("Deprecated cron job: remove 'Gocardless: Mandate Update Batch' from scheduled actions")
        pass
