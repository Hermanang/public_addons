# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
from werkzeug import urls
import logging
import datetime
import uuid


_logger = logging.getLogger(__name__)


class GC_Partner(models.Model):
    _inherit = 'res.partner'

    use_gc = fields.Boolean(compute='_compute_use_gc', store=False)

    @api.depends('gc_state')
    def _compute_use_gc(self):
        for rec in self:
            rec.use_gc = (rec.gc_state in ['pending', 'complete'])

    gc_state = fields.Selection(
        [
            ['setup', 'Awaiting Setup'],
            ['pending', 'Pending'],
            ['complete', 'Setup Complete']
        ],
        string="GoCardless setup state:",
        default='setup'
    )

    gc_mandate_state = fields.Selection(related='mandate_id.gc_state')
    gc_last_state_change = fields.Date("Last updated", default=datetime.date(year=1970, month=1, day=1))
    gc_mandate_id = fields.Char("GoCardless Mandate ID", related='mandate_id.gc_mandate_id', store=False)
    gc_redirect_flow_id = fields.Char()
    gc_redirect_url = fields.Char()
    gc_access_token = fields.Char()
    mandate_id = fields.Many2one(
        comodel_name='gocardless.mandate',
        string="GoCardless Mandate")

    def action_send_partner_email(self):
        self.send_partner_email(self)
        # self.write({
        #     'use_gc':    True
        # })

    def send_partner_email(self, partner, batch_run=False):
        # Obtenir la configuration GoCardless de la société du partenaire
        config = self.env['gocardless.config'].get_active_config(partner.company_id.id)
        if not config or not config.gc_access_token:
            raise UserError(
                "No active GoCardless configuration found for this company. "
                "Please configure GoCardless in the company settings."
            )

        gc_url = config.gc_custom_domain
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        # Vérifier le domaine personnalisé
        if type(gc_url) is str and gc_url:
            if urls.url_parse(url=gc_url).scheme in ['http', 'https']:
                base_url = gc_url

        _logger.debug("Got something to do: {}".format(partner.name))
        count = partner.invoice_ids.search_count([('partner_id', '=', partner.id), ('state', '!=', 'draft')])
        if count <= 0 and batch_run:
            return

        gc_token = str(uuid.uuid4())
        redirect_url = urls.url_join(base_url, '/gocardless/activate/?gc_access_token={}'.format(gc_token))
        partner.write({
            'gc_state': 'pending',
            'gc_last_state_change': datetime.date.today(),
            'gc_redirect_url': redirect_url,
            'gc_access_token': gc_token
        })

        # issue the email invite
        mail_template = self.env.ref('gocardless.gc_mandate_invite_email')
        self.env['mail.template'].browse(mail_template.id).send_mail(partner.id)

    def addPartnerBatchRun(self):

        date_last_week = datetime.date.today() - datetime.timedelta(days=7)
        for partner in self.search([('gc_state', 'in', ['pending', 'complete']),
                                    '|',
                                    ('gc_state', '=', 'setup'),
                                    '&',
                                    ('gc_state', '=', 'pending'),
                                    ('gc_last_state_change', '<', date_last_week),  # resubmit stale requests
                                    ]):
            self.send_partner_email(partner, batch_run=True)
