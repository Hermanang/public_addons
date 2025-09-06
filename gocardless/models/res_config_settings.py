# -*- coding: utf-8 -*-

from odoo import models, fields, api
from werkzeug import urls


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    gc_access_token = fields.Char("Access Token")

    gc_environment = fields.Selection([['sandbox', 'Sandbox'], ['live', 'Live']], "API environment", default='sandbox')
    gc_description = fields.Char("Description (to be shown on the GoCardless mandate page)")
    gc_webhook_secret = fields.Char("Secret (Optional, for verification of GoCardless callbacks)")
    gc_webhook_url = fields.Char("Webhook return URL")
    gc_custom_domain = fields.Char("Custom URL prefix (leave blank to use the default Odoo URL)")
    gc_keep_journal = fields.Boolean("Record GoCardless payments in an accounting journal?", default=False)

    def gocardless_connect(self):
        self.set_values()
        return {
            'type': 'ir.actions.act_url',
            'url': '/gocardless/oauth-begin',
            'target': 'self',
        }

    def do_full_event_refresh(self):
        return self.env['gocardless.event'].do_full_event_refresh()

    def get_default_journal(self):
        return self.env.ref('gocardless.journal_gocardless').id

    def get_journals_selection(self):
        ret = []
        for j in self.env['account.journal']:
            ret.append([j.id, j.name])
        return ret

    gc_journal_id = fields.Many2one(comodel_name='account.journal', string="Journal to record payments in")

    gc_client_id = fields.Char("Client ID")
    gc_client_secret = fields.Char("Client Secret")

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        ICPSudo = self.env['ir.config_parameter'].sudo()

        jid = ICPSudo.get_param('gocardless.gc_journal_id')

        kj = ICPSudo.get_param('gocardless.gc_keep_journal')

        res.update(
            gc_access_token=ICPSudo.get_param('gocardless.gc_access_token'),
            gc_environment=ICPSudo.get_param('gocardless.gc_environment'),
            gc_description=ICPSudo.get_param('gocardless.gc_description'),
            gc_webhook_secret=ICPSudo.get_param('gocardless.gc_webhook_secret'),
            gc_webhook_url=urls.url_join(ICPSudo.get_param('web.base.url'), '/gocardless/webhook/'),
            gc_custom_domain=ICPSudo.get_param('gocardless.gc_custom_domain'),
            gc_keep_journal=kj,
            gc_journal_id=int(jid) or False,
            gc_client_id=ICPSudo.get_param('gocardless.gc_client_id'),
            gc_client_secret=ICPSudo.get_param('gocardless.gc_client_secret')
        )
        return res

    # end get_values

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        ICPSudo = self.env['ir.config_parameter'].sudo()
        ICPSudo.set_param('gocardless.gc_access_token', self.gc_access_token)
        ICPSudo.set_param('gocardless.gc_environment', self.gc_environment)
        ICPSudo.set_param('gocardless.gc_description', self.gc_description)
        ICPSudo.set_param('gocardless.gc_webhook_secret', self.gc_webhook_secret)
        ICPSudo.set_param('gocardless.gc_custom_domain', self.gc_custom_domain)
        ICPSudo.set_param('gocardless.gc_keep_journal', self.gc_keep_journal)
        ICPSudo.set_param('gocardless.gc_journal_id', int(self.gc_journal_id.id))
        ICPSudo.set_param('gocardless.gc_client_id', self.gc_client_id)
        ICPSudo.set_param('gocardless.gc_client_secret', self.gc_client_secret)
