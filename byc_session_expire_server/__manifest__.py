# -*- coding: utf-8 -*-
{
    'name': 'Secure Server-Side Session Timeout | Inactivity Logout (Server Enforced)',
    'summary': 'Enforces a secure, server-side session timeout. Automatically terminates idle user sessions on the server, even if the browser is closed.',
    'description': """
# Secure Server-Side Session Timeout & Auto Logout

This module provides a robust, **server-enforced** mechanism to automatically terminate idle user sessions after a specified period of inactivity. Unlike client-side (JavaScript) solutions, this module operates entirely on the server. When a user who has been inactive for too long sends a new request to Odoo, the server checks the session's age and securely logs them out before processing the request.

This method is inherently more secure because it cannot be bypassed by disabling JavaScript or by closing the browser tab. It ensures that idle sessions are cleaned up, preventing unauthorized access on unattended workstations and helping organizations comply with strict IT security policies.

## Key Features

- **Server-Enforced Security:** Session validity is checked with every incoming request, making it impossible for an old, expired session to be reused.
- **Configurable Inactivity Limit:** Set a global inactivity period (e.g., 01:30 for 1 hour 30 minutes) from the General Settings menu.
- **Master Switch:** Easily enable or disable the entire feature with a single checkbox.
- **Administrator Exclusion:** Optionally prevent the Administrator's session from ever expiring, useful for system maintenance.
- **Targeted User Timeouts:** Configure the timeout to apply *only* to a specific list of users, leaving all others unaffected. This is perfect for applying stricter rules to certain roles.
- **No Client-Side Code:** Operates without any JavaScript, ensuring zero performance impact on the user's browser and compatibility with all devices.

## Installation & Configuration

1.  **Install the Module:** Add the `byc_session_expire_server` module to your addons path and install it from the Odoo Apps menu.
2.  **Configure in Settings:** Navigate to **Settings -> General Settings**. Scroll to the **"Server-Side Inactivity Timeout"** section.
3.  **Enable and Set Limit:**
    - Check "Enable Server-Side Session Timeout."
    - Set the desired "Inactivity Limit (HH:MM)".
    - Configure any optional settings like excluding the admin or targeting specific users.
    - Save the configuration.
4.  **How It Works:** Once configured, the module silently monitors session age. If a user is inactive beyond the limit, their very next interaction with Odoo (like clicking a menu) will trigger an immediate and secure logout, redirecting them to the login page.

## Use Cases & Keywords

This module is the ideal solution for environments requiring high security, such as those compliant with HIPAA, GDPR, or internal corporate policies.

Keywords: Server Session Timeout, Auto Logout, Inactive Session Logout, Secure Sign Out, Server-Side Session Expire, Backend Timeout, Odoo Session Security, Idle Session Terminator.

## Module Information

- **Category:** Tools / Security
- **Dependencies:** This module depends on `base` and `base_setup` (for integration into General Settings).
- **License:** AGPL-3 (As per original module)
- **Version:** 18.0.2.0.0 (Reflecting the new features)

## Support

**Author:** ByCorn Technologies
**Company:** ByCorn Technologies
**Support Contact:** For questions or issues, please contact support@bycorn.com.
**Website:** https://www.bycorn.com
""",
    'author': 'ByCorn Technologies',
    'company': 'ByCorn Technologies',
    'maintainer': 'ByCorn Technologies',
    'website': 'https://www.bycorn.com',
    'support': 'support@bycorn.com',
    'category': 'Tools',
    'version': '18.0.2.0.0', # Updated version for new features
    'license': 'AGPL-3', # Kept original license, change to 'OPL-1' if you want to sell it
    'depends': [
        'base',
        'base_setup', # Essential for res.config.settings with company_id
    ],
    'data': [
        # This data file will be removed in the next step
        'views/res_config_settings.xml',
    ],
    # This module has no client-side assets
    'assets': {},
    'images': [
        'static/description/banner.jpg',
    ],
    'installable': True,
    'application': False, # It's a tool, not a full application
}