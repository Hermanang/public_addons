from odoo import models, api, _
from odoo.exceptions import UserError


class GocardlessSetupWizard(models.TransientModel):

    _name = "gocardless.setup.wizard"
    _description = "Send mandate setup emails"

    def send_setup_email(self):
        ctx = dict(self._context or {})

        active_ids = ctx.get('active_ids', []) or []
        for r in self.env['res.partner'].browse(active_ids):
            if r.gc_state != 'setup':
                # don't double bump, just skip over silently
                continue

            r.action_send_partner_email()


class GocardlessChargeWizard(models.TransientModel):

    _name = "gocardless.charge.wizard"
    _description = "Take payments for invoices by GoCardless"

    def take_payment(self):
        ctx = dict(self._context or {})

        active_ids = ctx.get('active_ids', []) or []
        for r in self.env['account.move'].browse(active_ids):
            if (r.state != 'posted') or (r.payment_state != 'not_paid'):
                raise UserError('Only open invoices can be charged. Please make sure you have not selected draft or paid invoices, and try again.')
            if not r.gc_display_gc:
                raise UserError('One or more selected invoices are not eligible for GoCardless (have all selected customers completed GoCardless setup?)')
            if r.gc_payment_attempted:
                # don't double bump the payment - although idempotency should
                # protect the customer, this still results in a needless api call
                continue

            r.action_gocardless_take_payment()
