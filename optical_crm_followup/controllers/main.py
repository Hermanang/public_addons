# -*- coding: utf-8 -*-
import re

from odoo import http
from odoo.http import request
from odoo.tools import file_open


class OpticalFollowupGuide(http.Controller):
    """Sert le guide utilisateur illustré (data/user_guide.html) en exigeant
    une authentification.

    ``auth='user'`` redirige automatiquement vers la page de connexion si
    l'utilisateur n'est pas connecté — le guide n'est donc PAS public,
    contrairement aux fichiers ``/static/``. Un contrôle de groupe restreint
    en plus aux utilisateurs optiques.

    Les captures d'écran sont embarquées en base64 dans le fichier HTML
    (aucune requête d'image publique), ce qui évite d'exposer des noms de
    clients réels visibles sur certaines captures.
    """

    _GUIDE_PATH = 'optical_crm_followup/data/user_guide.html'

    # Bloc réservé aux responsables : retiré du HTML servi aux non-managers
    # (section « Paramétrer le plan de suivi » + son entrée de menu). Retrait
    # côté serveur → le contenu n'est PAS envoyé aux vendeurs (invisible même
    # dans le code source de la page).
    _MANAGER_BLOCK_RE = re.compile(
        r'<!--\s*MANAGER:START\s*-->.*?<!--\s*MANAGER:END\s*-->',
        re.DOTALL,
    )

    @http.route(
        '/optical_crm_followup/guide',
        type='http', auth='user', methods=['GET'], website=False,
    )
    def user_guide(self, **kwargs):
        if not request.env.user.has_group('optical.group_optical_user'):
            return request.not_found()
        with file_open(self._GUIDE_PATH, 'rb') as fp:
            content = fp.read().decode('utf-8')
        if not request.env.user.has_group('optical.group_optical_manager'):
            content = self._MANAGER_BLOCK_RE.sub('', content)
        content = content.encode('utf-8')
        return request.make_response(content, headers=[
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Content-Length', str(len(content))),
            ('X-Content-Type-Options', 'nosniff'),
        ])
