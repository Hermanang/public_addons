# -*- coding: utf-8 -*-
from odoo import http, models
from odoo.http import Response

import logging
import werkzeug
import json
import hmac
import hashlib
import datetime
import gocardless_pro

_logger = logging.getLogger(__name__)


from werkzeug import urls

class Gocardless(http.Controller):

    @http.route('/gocardless/oauth-begin', auth='user')
    def gc_oauth(self, **kw):
        # Obtenir la configuration GoCardless de la société de l'utilisateur
        user_company = http.request.env.user.company_id
        config = http.request.env['gocardless.config'].sudo().get_active_config(user_company.id)
        
        if not config:
            raise Exception("No active GoCardless configuration found for company: {}".format(user_company.name))
        
        # Configuration directe avec GoCardless
        if config.gc_environment == 'sandbox':
            base_url = 'https://connect-sandbox.gocardless.com'
        else:
            base_url = 'https://connect.gocardless.com'
        
        # Paramètres pour l'authentification OAuth directe
        params = {
            'client_id': config.gc_client_id,
            'redirect_uri': urls.url_join(http.request.env['ir.config_parameter'].sudo().get_param('web.base.url'), '/gocardless/auth-return?company_id={}'.format(user_company.id)),
            'response_type': 'code',
            'scope': 'read_write',
            'state': 'gocardless_oauth_{}'.format(user_company.id),
            'prefill': json.dumps({
                'company_name': user_company.display_name,
                'email': user_company.email
            })
        }
        
        auth_url = "{}?{}".format(urls.url_join(base_url, '/oauth/authorize'), urls.url_encode(params))
        return werkzeug.utils.redirect(auth_url)

    @http.route('/gocardless/auth-return', auth='user')
    def gc_oauth_return(self, **kw):
        # Récupérer l'ID de la société depuis les paramètres de la requête
        company_id = kw.get('company_id')
        if not company_id:
            _logger.error("No company_id parameter found in OAuth return")
            return werkzeug.utils.redirect("/")
        
        # Obtenir la configuration GoCardless de la société
        config = http.request.env['gocardless.config'].sudo().get_active_config(int(company_id))
        if not config:
            _logger.error("No active GoCardless configuration found for company ID: %s", company_id)
            return werkzeug.utils.redirect("/")
        
        if kw.get('code'):
            # Échanger le code d'autorisation contre un token d'accès
            if config.gc_environment == 'sandbox':
                token_url = 'https://connect-sandbox.gocardless.com/oauth/access_token'
            else:
                token_url = 'https://connect.gocardless.com/oauth/access_token'
            
            # Préparer les données pour l'échange de token
            data = {
                'client_id': config.gc_client_id,
                'client_secret': config.gc_client_secret,
                'grant_type': 'authorization_code',
                'code': kw.get('code'),
                'redirect_uri': urls.url_join(http.request.env['ir.config_parameter'].sudo().get_param('web.base.url'), '/gocardless/auth-return?company_id={}'.format(company_id))
            }
            
            # Faire la requête pour obtenir le token
            import requests
            response = requests.post(token_url, data=data)
            
            if response.status_code == 200:
                token_data = response.json()
                access_token = token_data.get('access_token')
                
                # Stocker le token d'accès dans la configuration de la société
                config.write({
                    'gc_access_token': access_token
                })
                
                client = gocardless_pro.Client(
                    access_token=access_token,
                    environment=config.gc_environment
                )
                
                # Vérifier le statut du créancier
                try:
                    creditor = client.creditors.list().records[0]
                    if creditor.verification_status == 'action_required':
                        return werkzeug.utils.redirect("https://verify{}.gocardless.com".format(
                            ('-sandbox' if config.gc_environment == 'sandbox' else '')
                        ))
                except Exception as e:
                    _logger.error("Error checking creditor status: %s", str(e))
        
        return werkzeug.utils.redirect("/odoo/gocardless-accounts")
        # return werkzeug.utils.redirect("/web#action=gocardless.config_action&view_type=form&id={}".format(config.id))

    @http.route('/gocardless/return/', auth='public')
    def gc_return(self, **kw):
        # Trouver la configuration basée sur le partenaire
        partner = http.request.env['res.partner'].sudo().search([
            ('gc_redirect_flow_id', '=', kw.get('redirect_flow_id'))
        ], limit=1)
        
        if not partner:
            _logger.error("No partner found for redirect_flow_id: %s", kw.get('redirect_flow_id'))
            return werkzeug.utils.redirect("/")
        
        # Obtenir la configuration GoCardless de la société du partenaire
        config = http.request.env['gocardless.config'].sudo().get_active_config(partner.company_id.id)
        if not config:
            _logger.error("No active GoCardless config found for company: %s", partner.company_id.name)
            return werkzeug.utils.redirect("/")
        
        client = gocardless_pro.Client(
            access_token=config.gc_access_token,
            environment=config.gc_environment
        )
        
        redirect_flow = client.redirect_flows.complete(
            kw.get('redirect_flow_id'),
            params={
                "session_token": partner.gc_access_token
            }
        )
        
        m = http.request.env['gocardless.mandate'].sudo().create({
            'gc_mandate_id': redirect_flow.links.mandate,
            'gc_state': 'pending',
            'partner_id': partner.id,
            'config_id': config.id,
            'gc_last_state_change': datetime.date.today()
        })
        
        partner.write({
            'gc_state': 'complete',
            'mandate_id': m.id
        })
        partner.message_post(body="GoCardless: Setup complete, mandate ID: {}".format(redirect_flow.links.mandate))            
        
        return werkzeug.utils.redirect(redirect_flow.confirmation_url)
    #end gc_return

    @http.route('/gocardless/activate/', auth='public')
    def gc_activate(self, **kw):
        # Trouver le partenaire basé sur le token d'accès
        partner = http.request.env['res.partner'].sudo().search([
            ('gc_access_token', '=', kw.get('gc_access_token'))
        ], limit=1)
        
        if not partner:
            _logger.error("No partner found for access token: %s", kw.get('gc_access_token'))
            return werkzeug.utils.redirect("/")
        
        # Obtenir la configuration GoCardless de la société du partenaire
        config = http.request.env['gocardless.config'].sudo().get_active_config(partner.company_id.id)
        if not config:
            _logger.error("No active GoCardless config found for company: %s", partner.company_id.name)
            return werkzeug.utils.redirect("/")
        
        client = gocardless_pro.Client(
            access_token=config.gc_access_token,
            environment=config.gc_environment
        )
        
        gc_url = config.gc_custom_domain
        base_url = http.request.env['ir.config_parameter'].sudo().get_param('web.base.url')
        
        # Vérifier le domaine personnalisé
        if type(gc_url) is str and gc_url:
            if urls.url_parse(url=gc_url).scheme in ['http', 'https']:
                base_url = gc_url
        
        split_name = str(partner.name).split(" ", 1)
        redirect_flow = client.redirect_flows.create(params={
            'description': config.gc_description if config.gc_description else '',
            'session_token': partner.gc_access_token,
            'success_redirect_url': urls.url_join(base_url, '/gocardless/return/'),
            'prefilled_customer': {
                "given_name": "" if len(split_name) < 1 else split_name[0],
                "family_name": "" if len(split_name) < 2 else split_name[1],                    
                'email': partner.email,
                "address_line1": partner.street if partner.street else '',
                "address_line2": partner.street2 if partner.street2 else '',
                "city": partner.city if partner.city else '',
                "postal_code": partner.zip if partner.zip else '',
                "country_code": partner.country_id.code if partner.country_id.code else ''
            }
        })
        
        _logger.info("Redirect URL generated: {}".format(redirect_flow.redirect_url))

        partner.write({
            'gc_state': 'pending',
            'gc_last_state_change': datetime.date.today(), 
            'gc_redirect_flow_id': redirect_flow.id
        })

        return werkzeug.utils.redirect(redirect_flow.redirect_url)
