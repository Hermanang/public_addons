# -*- coding: utf-8 -*-

from odoo import models, fields, exceptions
import logging

_logger = logging.getLogger(__name__)

class GCPayment(models.Model):
    _name = 'gocardless.payment'
    _description = 'GoCardless Payment'
    _check_company_auto = True
    
    _rec_name   = 'gc_payment_id'

    config_id = fields.Many2one(
        'gocardless.config', 
        string='Configuration',
        required=True,
        default=lambda self: self.env['gocardless.config'].get_default_config(),
        ondelete='restrict',
        help="GoCardless configuration this payment belongs to"
    )
    company_id = fields.Many2one(
        'res.company', 
        string='Company', 
        related='config_id.company_id', 
        store=True,
        readonly=True,
        index=True
    )

    amount = fields.Float("Transaction amount")
    
    claim_date  = fields.Datetime("Date claimed")
    post_date   = fields.Datetime("Date posted")
    payout_date = fields.Datetime("Date paid out")

    gc_payment_state = fields.Selection([
        ['pending','Pending'],
        ['created','Created'],
        ['pending_customer_approval','Pending Customer Approval'],
        ['customer_approval_granted','Customer approval: Granted'],
        ['customer_approval_rejected','Customer approval: Rejected'],
        ['customer_approval_denied', 'Customer approval: Denied'],
        ['pending_submission','Pending Submission'],
        ['submitted','Submitted'],
        ['confirmed','Confirmed'],
        ['cancelled','Cancelled'],
        ['failed','Failed'],
        ['charged_back','Charged back'],
        ['chargeback_cancelled','Chargeback cancelled'],
        ['paid_out','Paid out'],
        ['late_failure_settled','Late failure settled'],
        ['chargeback_settled','Chargeback settled'],
        ['resubmission_requested','Resubmission requested']        
    ], 
        string="Payment State",
        default='created'
    )

    last_state_change = fields.Datetime("Last state change on")
    gc_payment_id = fields.Char("Transaction ID")
    invoice_id = fields.Many2one('account.move')
    mandate_id  = fields.Many2one(comodel_name='gocardless.mandate',string='Mandate')
    event_ids   = fields.One2many(comodel_name='gocardless.event', inverse_name='payment_id', string="Events")

    
    def updatePaymentsBatchRun(self):
        # Method no longer used - keeping its stub to avoid
        # unnecessary cron exceptions
        _logger.warning("Deprecated cron job: remove 'Gocardless: Payment Update Batch' from scheduled actions")        
        pass

    
    def retry_payment(self):
        config = self.config_id
        if not config or not config.gc_access_token:
            raise exceptions.UserError("No active GoCardless configuration found")
            
        client = self.env['gocardless_pro.client'].get_client(config)

        ret = False
        try:
            ret = client.payments.retry(self.gc_payment_id)
        except self.env['gocardless_pro.errors'].ApiError as inst:
            raise exceptions.UserError(
                "The payment retry could not be completed for the following reason: {}"
                .format(
                    inst.message
                )
            )
            return

        self.write({'gc_payment_state': 'pending'})
        return ret
        

    
    def gc_cancel_payment(self):
        config = self.config_id
        if not config or not config.gc_access_token:
            raise exceptions.UserError("No active GoCardless configuration found")
            
        client = self.env['gocardless_pro.client'].get_client(config)

        try:
            client.payments.cancel(self.gc_payment_id)
        except self.env['gocardless_pro.errors'].ApiError as inst:
            raise exceptions.UserError(
                "The payment could not be cancelled for the following reason: {}"
                .format(
                    inst.message
                )
            )
