# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "Project Management System",
    'summary': """Bridge module for project""",
    'description': """
Bridge module for project and enterprise
    """,
    'category': 'Services/Project',
    'version': '1.0',
    'depends': ['project', 'web_timeline'],
    'data': [
        'security/ir.model.access.csv',
        'views/project_task_views.xml',
        'views/project_views.xml',
        'views/project_sharing_views.xml',
        'report/project_report_views.xml',
        'wizard/task_confirm_schedule_wizard_views.xml',
    ],
    'demo': ['data/project_demo.xml'],
    'auto_install': True,
    'license': 'AGPL-3',
    'assets': {
        'web.assets_backend': [
            '/project_management_system/static/src/scss/project_timeline.scss'
        ],
        'project.webclient': [
            'project_management_system/static/src/project_sharing/**/*',
        ],
    }
}
