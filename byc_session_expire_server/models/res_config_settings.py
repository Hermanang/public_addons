# -*- coding: utf-8 -*-
from odoo import models, fields

# Step 1: Add fields to the permanent storage model (res.company)
class ResCompany(models.Model):
    _inherit = 'res.company'

    byc_server_enable_auto_session_logout = fields.Boolean(
        string='Enable Auto Session Expire',
        help="Toggle to enable automatic expiration of inactive sessions."
    )
    byc_server_session_expire_limit = fields.Float(
        string='Session Expire Limit (Minutes)',
        default=60.0,
        help="Specify the period (in minutes) of inactivity after which users will be automatically logged out."
    )
    byc_server_exclude_admin_from_session_expire = fields.Boolean(
        string='Exclude Administrator from Session Expire',
        help="If enabled, the Administrator user will be excluded from automatic session expiration."
    )
    byc_server_enable_user_specific_session_expire = fields.Boolean(
        string="Enable User-Specific Session Expire",
        help="Enable to set session expiration for specific users."
    )
    byc_server_user_specific_session_expire_users = fields.Many2many(
        "res.users",
        string="Users with Specific Session Expire",
        help="Select users who will have specific session expiration settings.",
        domain="[('share', '=', False)]"
    )
    byc_server_enable_time_window = fields.Boolean(
        string='Enable Time Window Restriction',
        default=False,
        help="Enable to restrict login to specific time windows"
    )
    byc_server_start_time = fields.Float(
        string='Start Time (HH:MM)',
        default=8.0,
        help="Earliest allowed login time (in hours, e.g. 8.5 for 8:30 AM)"
    )
    byc_server_end_time = fields.Float(
        string='End Time (HH:MM)',
        default=18.0,
        help="Latest allowed login time (in hours, e.g. 18.0 for 6:00 PM)"
    )

# Step 2: Add fields to the settings interface model (res.config.settings)
class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    byc_server_enable_auto_session_logout = fields.Boolean(
        string='Enable Auto Session Expire',
        related='company_id.byc_server_enable_auto_session_logout',
        readonly=False
    )
    byc_server_session_expire_limit = fields.Float(
        string='Session Expire Limit (Minutes)',
        related='company_id.byc_server_session_expire_limit',
        readonly=False
    )
    byc_server_exclude_admin_from_session_expire = fields.Boolean(
        string='Exclude Administrator from Session Expire',
        related='company_id.byc_server_exclude_admin_from_session_expire',
        readonly=False
    )
    byc_server_enable_user_specific_session_expire = fields.Boolean(
        string="Enable User-Specific Session Expire",
        related="company_id.byc_server_enable_user_specific_session_expire",
        readonly=False
    )
    byc_server_user_specific_session_expire_users = fields.Many2many(
        related="company_id.byc_server_user_specific_session_expire_users",
        readonly=False
        )
    
    byc_server_enable_time_window = fields.Boolean(
        string='Enable Time Window Restriction',
        related='company_id.byc_server_enable_time_window', 
        readonly=False,
        help="Enable to restrict login to specific time windows"
    )
    byc_server_start_time = fields.Float(
        string='Start Time (HH:MM)',
        related='company_id.byc_server_start_time',
        readonly=False,
        help="Earliest allowed login time (in hours, e.g. 8.5 for 8:30 AM)"
    )
    byc_server_end_time = fields.Float(
        string='End Time (HH:MM)',
        related='company_id.byc_server_end_time',
        readonly=False,
        help="Latest allowed login time (in hours, e.g. 18.0 for 6:00 PM)"
    )
