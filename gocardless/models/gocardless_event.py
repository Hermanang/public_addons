# -*- coding: utf-8 -*-

from odoo import models, fields
import logging
import datetime

_logger = logging.getLogger(__name__)


class GC_Event(models.Model):
    _name = 'gocardless.event'
    _description = 'GoCardless Event'
    _rec_name = 'event_id'

    config_id = fields.Many2one(
        'gocardless.config',
        string='Configuration',
        required=True,
        default=lambda self: self.env['gocardless.config'].get_default_config(),
        ondelete='restrict',
        help="GoCardless configuration this event belongs to"
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='config_id.company_id',
        store=True,
        readonly=True,
        index=True
    )

    event_id = fields.Char(string="GoCardless Event ID")
    action = fields.Char(string="Action")
    created_at = fields.Datetime(string="Event Date")

    cause = fields.Char(string="Reason")
    ev_description = fields.Char(string="Reason Description")

    ev_origin = fields.Selection(
        selection=[
            ('bank', 'Bank'),
            ('gocardless', 'GoCardless'),
            ('api', 'API'),
            ('customer', 'Customer'),
            ('payer', 'Payer')
        ],
        string="Event origin"
    )

    ev_reason_code = fields.Char(string="Bank Reason Code")
    ev_scheme = fields.Char(string="Direct Debit Scheme")

    resource_type = fields.Selection(
        selection=[
            ('payments', 'Payment'),
            ('mandates', 'Mandate'),
            ('payouts', 'Payout'),
            ('refunds', 'Refunds'),
            ('subscriptions', 'Subscriptions'),
            ('creditors', 'Creditors'),
            ('billing_requests', 'Billing Requests'),
            ('instalment_schedules', 'Instalment Schedule'),
            ('payer_authorisations', 'Payer Authorisation')
        ],
        string="Resource type"
    )

    payment_id = fields.Many2one(comodel_name='gocardless.payment', string="Payment")
    mandate_id = fields.Many2one(comodel_name='gocardless.mandate', string="Mandate")

    def do_full_event_refresh(self):
        self.process_events()

    def doEvents(self):
        # we're in the batch run, so pick up the last 14 days
        date_cutoff = "{}T{}Z".format(datetime.date.today() - datetime.timedelta(days=14), datetime.datetime.min.time())
        self.process_events(date_cutoff)

    def process_events(self, date_cutoff=None):
        # Traiter les événements pour chaque configuration active
        active_configs = self.env['gocardless.config'].search([('is_active', '=', True)])

        total_count = 0
        for config in active_configs:
            if not config.gc_access_token:
                _logger.warning("Skipping config %s - no access token", config.name)
                continue

            _logger.info("Processing events for config: %s", config.name)

            client = self.env['gocardless_pro.client'].get_client(config)

            try:
                events = client.events.list(
                    params={
                        "created_at[gte]": date_cutoff
                    } if date_cutoff else {
                        "limit": 500
                    }
                ).records

                count = 0
                for event in events:
                    # Heavy lifting loop. Should probably look at refactoring this into an event dispatcher.
                    # Actually yeah, that's a good idea.
                    # Edit: we did it.

                    # anyway, to business.

                    existing_event = False

                    # first, make sure we don't already have the event ID in the database.
                    if len(self.search([('event_id', '=', event.id)])._ids) > 0:
                        # event already exists (length of search result > 0),
                        # so get on with the next one
                        existing_event = self.env['gocardless.event'].sudo().search([('event_id', '=', event.id)],
                                                                                    limit=1)

                    # parse the date into a format Python (and thus Odoo) actually likes:
                    eventDate = datetime.datetime.strptime(event.created_at, "%Y-%m-%dT%H:%M:%S.%fZ")

                    if not existing_event:
                        # let's go ahead and create the event
                        self.env['gocardless.event'].sudo().create({
                            'event_id': event.id,
                            'action': event.action,
                            'created_at': eventDate,
                            'cause': event.details.cause,
                            'ev_description': event.details.description,
                            'ev_origin': event.details.origin,
                            'ev_reason_code': event.details.reason_code,
                            'ev_scheme': event.details.scheme,
                            'resource_type': event.resource_type,
                            'config_id': config.id,  # Assigner la configuration
                            'mandate_id': self.env['gocardless.mandate'].search(
                                [('gc_mandate_id', '=', event.links.mandate)],
                                limit=1).id if event.resource_type == 'mandates' else None,
                            'payment_id': self.env['gocardless.payment'].search(
                                [('gc_payment_id', '=', event.links.payment)],
                                limit=1).id if event.resource_type == 'payments' else None
                        })
                    else:
                        # event already exists
                        # are we in a reprocess? let's work this out from what we know
                        if date_cutoff:
                            # there's a cutoff date specified, so no we're not
                            continue
                        else:
                            # we're in a reprocess, update the event
                            existing_event.write({
                                'event_id': event.id,
                                'action': event.action,
                                'created_at': eventDate,
                                'cause': event.details.cause,
                                'ev_description': event.details.description,
                                'ev_origin': event.details.origin,
                                'ev_reason_code': event.details.reason_code,
                                'ev_scheme': event.details.scheme,
                                'resource_type': event.resource_type,
                                'config_id': config.id,  # Mettre à jour la configuration
                                'mandate_id': self.env['gocardless.mandate'].search(
                                    [('gc_mandate_id', '=', event.links.mandate)],
                                    limit=1).id if event.resource_type == 'mandates' else None,
                                'payment_id': self.env['gocardless.payment'].search(
                                    [('gc_payment_id', '=', event.links.payment)],
                                    limit=1).id if event.resource_type == 'payments' else None
                            })

                    if event.resource_type == 'payments':
                        self.dispatchPaymentEvents(event)
                    elif event.resource_type == 'mandates':
                        self.dispatchMandateEvents(event)
                    # endif

                    count += 1
                    total_count += 1

                _logger.info('Processed {} events for config {}'.format(count, config.name))

            except Exception as e:
                _logger.error("Error processing events for config %s: %s", config.name, str(e))
                continue

        _logger.info('Total processed {} events'.format(total_count))

    def dispatchPaymentEvents(self, event):
        ICPSudo = self.env['ir.config_parameter'].sudo()

        post_journals = ICPSudo.get_param('gocardless.gc_keep_journal')
        jid = ICPSudo.get_param('gocardless.gc_journal_id')
        journal = self.env['account.journal'].search([('id', '=', jid)])

        gc_payments = self.env['gocardless.payment'].sudo().search([('gc_payment_id', '=', event.links.payment)])
        for gc_payment in gc_payments:
            eventDate = datetime.datetime.strptime(event.created_at, "%Y-%m-%dT%H:%M:%S.%fZ")
            if (gc_payment.gc_payment_state != event.action) and (eventDate > (fields.Datetime.from_string(
                    gc_payment.last_state_change) if gc_payment.last_state_change else datetime.datetime(1970, 1, 1))):
                # let's check we actually need to update something (disabled for debug)
                # pick up the previous state
                prev_state = gc_payment.gc_payment_state
                vals = {
                    'gc_payment_state': event.action
                }

                # updated logic to catch missed 'confirmed' events
                if (event.action == 'confirmed') or (event.action == 'paid_out' and prev_state != 'confirmed'):
                    vals.update({'post_date': eventDate})

                    if post_journals:
                        gc_payment.invoice_id.processPaymentEvent(event, gc_payment, journal)
                    # endif
                # endif

                if event.action == 'paid_out':
                    vals.update({'payout_date': eventDate})

                vals.update({'last_state_change': eventDate})
                gc_payment.write(vals)

                msg = "Payment update: Payment ID {} State: {} Amount: {}".format(gc_payment.gc_payment_id,
                                                                                  gc_payment.gc_payment_state,
                                                                                  gc_payment.amount)
                gc_payment.invoice_id.message_post(body=msg)

        pass

    def dispatchMandateEvents(self, event):

        for mandate in self.env['gocardless.mandate'].sudo().search([('gc_mandate_id', '=', event.links.mandate)]):
            eventDate = datetime.datetime.strptime(event.created_at, "%Y-%m-%dT%H:%M:%S.%fZ")
            if event.action == 'mandate_replaced':
                mandate.write({
                    'gc_mandate_id': event.links.new_mandate,
                    'gc_last_state_change': eventDate
                })
                return

            if (mandate.gc_state != event.action) and (
                    eventDate > fields.Datetime.from_string(mandate.gc_last_state_change)):
                # let's check we actually need to update something (disabled for debug)
                mandate.write({
                    'gc_state': event.action,
                    'gc_last_state_change': eventDate
                })
                msg = "GoCardless: Mandate ID {} changed state to {}".format(mandate.gc_mandate_id, mandate.gc_state)
                mandate.partner_id.message_post(body=msg)
