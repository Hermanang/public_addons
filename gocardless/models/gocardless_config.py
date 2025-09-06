# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions
import logging
from werkzeug import urls

_logger = logging.getLogger(__name__)

class GocardlessConfig(models.Model):
    _name = 'gocardless.config'
    _description = 'GoCardless Configuration'
    _check_company_auto = True
    _rec_name = 'display_name'

    name = fields.Char(string='Configuration Name', required=True, help="Internal name for this GoCardless configuration")
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)
    company_id = fields.Many2one(
        'res.company', 
        string='Company', 
        required=True, 
        default=lambda self: self.env.company,
        help="Company this configuration belongs to"
    )
    is_active = fields.Boolean(string='Active', default=True, help="Enable or disable this configuration")
    
    # Credentials GoCardless
    gc_access_token = fields.Char(string='Access Token', help="GoCardless API access token")
    gc_environment = fields.Selection(
        [('sandbox','Sandbox'),('live','Live')], 
        string='API Environment', 
        default='sandbox',
        help="Choose between Sandbox (testing) and Live (production) environments"
    )
    gc_client_id = fields.Char(string='Client ID', help="GoCardless OAuth client ID")
    gc_client_secret = fields.Char(string='Client Secret', help="GoCardless OAuth client secret")
    
    # Configuration générale
    gc_description = fields.Char(
        string='Mandate Description', 
        help="Description that will appear on customer mandate forms"
    )
    gc_webhook_secret = fields.Char(
        string='Webhook Secret', 
        help="Secret key for verifying GoCardless webhook requests (optional)"
    )
    gc_custom_domain = fields.Char(
        string='Custom Domain', 
        help="Custom domain for customer redirects (leave blank to use Odoo base URL)"
    )
    
    # URL de redirection OAuth (calculée)
    gc_redirect_uri = fields.Char(
        string='OAuth Redirect URI',
        compute='_compute_gc_redirect_uri',
        readonly=True,
        help="URL to configure in GoCardless dashboard for OAuth callbacks"
    )
    
    # Journal comptable
    gc_keep_journal = fields.Boolean(
        string='Record Payments in Journal', 
        default=False,
        help="Record GoCardless payments in accounting journal"
    )
    gc_journal_id = fields.Many2one(
        'account.journal', 
        string='Payment Journal', 
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]",
        check_company=True,
        help="Accounting journal to record GoCardless payments"
    )
    
    # Relations
    payment_ids = fields.One2many('gocardless.payment', 'config_id', string='Payments')
    mandate_ids = fields.One2many('gocardless.mandate', 'config_id', string='Mandates')
    event_ids = fields.One2many('gocardless.event', 'config_id', string='Events')

    # Contraintes d'unicité
    _sql_constraints = [
        ('company_unique', 'unique(company_id)', 'Only one GoCardless configuration per company is allowed'),
    ]

    @api.depends('name', 'company_id')
    def _compute_display_name(self):
        for config in self:
            if config.company_id:
                config.display_name = f"{config.name} ({config.company_id.name})"
            else:
                config.display_name = config.name

    @api.depends('company_id')
    def _compute_gc_redirect_uri(self):
        """Calcule l'URL de redirection OAuth pour cette configuration"""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for config in self:
            if config.company_id:
                config.gc_redirect_uri = urls.url_join(
                    base_url, 
                    '/gocardless/auth-return?company_id={}'.format(config.company_id.id)
                )
            else:
                config.gc_redirect_uri = False

    @api.model
    def get_active_config(self, company_id=None):
        """Retourne la configuration active pour une société"""
        if company_id is None:
            company_id = self.env.company.id
        
        return self.search([
            ('company_id', '=', company_id),
            ('is_active', '=', True)
        ], limit=1)

    def action_test_connection(self):
        """Teste la connexion à l'API GoCardless"""
        self.ensure_one()
        try:
            import gocardless_pro
            client = gocardless_pro.Client(
                access_token=self.gc_access_token,
                environment=self.gc_environment
            )
            # Test simple de connexion
            client.creditors.list(limit=1)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Connection Successful',
                    'message': 'GoCardless connection test passed successfully.',
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            raise exceptions.UserError(f"Connection test failed: {str(e)}")

    def gocardless_connect(self):
        """Lance le processus OAuth pour cette configuration"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/gocardless/oauth-begin',
            'target': 'self',
        }

    @api.model
    def get_default_config(self):
        """Retourne la configuration par défaut pour la société courante"""
        return self.get_active_config()
