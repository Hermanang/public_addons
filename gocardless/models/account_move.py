# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions
import logging
import datetime
import time

_logger = logging.getLogger(__name__)


class Invoice(models.Model):
    _inherit = 'account.move'

    # Odoo 13 compatibility thunks
    number = fields.Char(related='name', store=False)
    gc_last_payment_attempt = fields.Datetime("Date of last payment attempt", copy=False)
    gc_payment_attempted = fields.Boolean("GC Charged", copy=False)

    # calculate default value for pay_by_gc
    def _gc_get_pay_by_gc(self):
        for rec in self:
            return rec.partner_id.use_gc

    # gc_pay_by_gc = fields.Boolean("Take payment for this invoice by GoCardless", default=_gc_get_pay_by_gc)

    gc_retry_payment = fields.Boolean("Retry payment?", copy=False)
    gc_enable_payment_recreate = fields.Boolean("Recreate payment available", default=False, copy=False)
    gc_payments = fields.One2many(string="Payment Records", comodel_name='gocardless.payment',
                                  inverse_name='invoice_id', copy=False)

    active_payment_id = fields.Many2one(comodel_name='gocardless.payment', string='Current Payment', copy=False)
    gc_display_gc = fields.Boolean(string="GoCardless Chargeable", store=False, compute='_compute_display_gc',
                                   search='_display_gc_search', copy=False)

    @api.depends('partner_id', 'company_id')
    def _compute_display_gc(self):
        for rec in self:
            config = self.env['gocardless.config'].get_active_config(rec.company_id.id)
            if config and config.gc_access_token:
                rec.gc_display_gc = (rec.partner_id.gc_state not in ['setup', 'pending'])
            else:
                rec.gc_display_gc = False

    def _display_gc_search(self, operator, value):
        if (operator == '=' and value) or (operator == '!=' and not value):
            domain = ([('partner_id.gc_state', 'not in', ['setup', 'pending'])])
        else:
            domain = ([('partner_id.gc_state', 'in', ['setup', 'pending'])])

        recs = self.search(domain)
        if recs:
            return [('id', 'in', [x.id for x in recs])]

    @api.onchange('partner_id')
    def _onchange_partner(self):
        # self.gc_pay_by_gc = self.partner_id.use_gc
        pass

    def action_gocardless_retry_payment(self):
        oops = False
        try:
            return self.active_payment_id.retry_payment()
        except exceptions.UserError as inst:
            _logger.debug("OOPS")
            oops = inst
            if "inactive mandate" in inst.message:
                _logger.debug("Enabling recreate button")
                self.gc_enable_payment_recreate = True
                self.write({
                    'gc_enable_payment_recreate': True
                })
                self.env.cr.commit()
        finally:
            if oops:
                _logger.debug("We got an oops, raising it")
                raise oops
        # self.gc_retry_payment = True
        # return self.action_gocardless_take_payment()

    def action_gocardless_recreate_payment(self):
        self.gc_retry_payment = True
        return self.action_gocardless_take_payment()

    def action_gocardless_take_payment(self):
        invoice = self

        # Obtenir la configuration GoCardless de la société de la facture
        config = self.env['gocardless.config'].get_active_config(invoice.company_id.id)
        if not config or not config.gc_access_token:
            raise exceptions.UserError(
                "No active GoCardless configuration found for this company. "
                "Please configure GoCardless in the company settings."
            )

        client = self.env['gocardless_pro.client'].get_client(config)

        try:
            payment = client.payments.create(
                params={
                    "amount": int((invoice.amount_total * 100)),  # format amount in cents
                    "app_fee": int((invoice.amount_total * 100) * 0.01),
                    # DO NOT MODIFY THIS LINE, IT IS HOW WE GET PAID FOR OUR WORK. MODIFYING THIS LINE WILL VOID YOUR SUPPORT.
                    "currency": invoice.currency_id.name,
                    "retry_if_possible": True,
                    "links": {
                        "mandate": invoice.partner_id.gc_mandate_id
                    },
                    "metadata": {
                        "invoice_number": invoice.number
                    }
                },
                headers={
                    'Idempotency-Key': '{}-{}'.format(invoice.partner_id.gc_mandate_id,
                                                      invoice.number) if not invoice.gc_retry_payment else 'retry-{}-{}-{}'.format(
                        invoice.partner_id.gc_mandate_id, invoice.number, datetime.datetime.now())
                    # this key allows us to set a unique id for the tx in question
                    # - making sure we don't accidentally bill a partner twice
                }
            )
        except self.env['gocardless_pro.errors'].ApiError as inst:
            raise exceptions.Warning(
                "Payment could not be submitted to GoCardless for the following reason: {}"
                    .format(inst.message)
            )

        invoice.write({
            'gc_last_payment_attempt': datetime.datetime.now(),
            'gc_payment_attempted': True,  # we've attempted to take payment
            'gc_retry_payment': False,  # if we've done a manual retry, cancel this too
            'gc_enable_payment_recreate': False  # we definitely want to cancel this one
        })

        mandate = self.env['gocardless.mandate'].search([('gc_mandate_id', '=', invoice.partner_id.gc_mandate_id)],
                                                        limit=1)

        p = self.env['gocardless.payment'].sudo().create({
            'amount': invoice.amount_total,
            'claim_date': datetime.datetime.now(),
            'mandate_id': mandate.id,
            'gc_payment_state': 'pending',
            'gc_payment_id': payment.id,
            'invoice_id': invoice.id
        })

        invoice.write({
            'active_payment_id': p.id
        })

        invoice.message_post(body="GoCardless payment requested for {} {} with payment ID {}".format(
            invoice.currency_id.name, invoice.amount_total, payment.id
        ))
        time.sleep(0.1)  # important to avoid GoCardless API flooding & rate limit exceptions

    def takePaymentBatchRun(self):
        _logger.warning("Deprecated cron job: remove 'Gocardless: Invoice Take Payment Batch' from scheduled actions")
        pass

    def processPaymentEvent(self, event, gc_payment, journal):
        payment = self.env['account.payment.register'].with_context(active_model='account.move', active_ids=[self.id])
        payment.create({
            'payment_type': 'inbound',
            'amount': gc_payment.amount,
            'payment_date': datetime.date.today(),
            'journal_id': int(journal.id),
            'currency_id': int(self.currency_id.id),
            'communication': self.number,
            'partner_type': 'customer',  # TODO: sort out the hardcoded bit here if needed
            'partner_id': int(self.partner_id.id),
        }).action_create_payments()
