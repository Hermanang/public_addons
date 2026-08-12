# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.tools import file_open


class OpticalWizardGuide(http.Controller):
    """Sert le guide utilisateur illustré (data/user_guide_prise_commande.html).

    ``auth='user'`` redirige automatiquement vers la page de connexion si
    l'utilisateur n'est pas connecté. Un contrôle de groupe restreint
    l'accès aux utilisateurs optiques.

    Les captures sont embarquées en base64 dans le HTML (aucune requête
    d'image publique), ce qui évite d'exposer des noms de clients réels
    visibles sur certaines captures.
    """

    _GUIDE_PATH = 'optical/data/user_guide_prise_commande.html'

    @http.route(
        '/optical/guide/prise-commande',
        type='http', auth='user', methods=['GET'], website=False,
    )
    def user_guide(self, **kwargs):
        if not request.env.user.has_group('optical.group_optical_user'):
            return request.not_found()
        with file_open(self._GUIDE_PATH, 'rb') as fp:
            content = fp.read()
        return request.make_response(content, headers=[
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Content-Length', str(len(content))),
            ('X-Content-Type-Options', 'nosniff'),
        ])
