{
    'name': 'Helpdesk Type-aware Stage Validation',
    'version': '18.0.1.0.0',
    'category': 'Helpdesk',
    'summary': 'Filtrer les validations de stage par type de ticket helpdesk',
    'author': 'Otiten',
    'website': 'https://www.otiten.com',
    'license': 'LGPL-3',
    'description': """
Bridge entre helpdesk_type et helpdesk_mgmt_stage_validation.

Ajoute un champ "Types concernés" sur les stages helpdesk : la validation
des champs configurée dans helpdesk_mgmt_stage_validation peut être
restreinte aux tickets de certains types uniquement.

Cas d'usage : "Stage Cloturé requiert proposed_solution UNIQUEMENT pour
les tickets de type Réclamation". Les tickets de type SAV ou Renseignement
peuvent être clôturés sans proposed_solution.

Sans ce bridge, helpdesk_mgmt_stage_validation applique la validation à
tous les tickets sans distinction de type.
    """,
    'depends': [
        'helpdesk_mgmt_stage_validation',
        'helpdesk_type',
    ],
    'data': [
        'views/helpdesk_ticket_stage_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
