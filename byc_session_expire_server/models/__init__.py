# -*- coding: utf-8 -*-
"""
Models for User Session Inactivity Timeout Module
...
"""

# Import the models for company and general settings configuration
from . import res_config_settings # <<< ADD THIS LINE

# Import the model that extends 'res.users' to add session timeout checks
from . import res_users

# Import the model that extends 'ir.http' to intercept HTTP requests
from . import ir_http

