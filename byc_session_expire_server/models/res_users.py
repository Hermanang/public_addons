# -*- coding: utf-8 -*-
import logging
from os.path import getmtime
from time import time

from odoo import api, http, models
from odoo.http import SessionExpiredException

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    def _should_session_expire(self):
        """
        Checks if THIS specific user's session should expire.
        'self' is expected to be a single user record.
        """
        self.ensure_one()
        company = self.env.company
        
        if not company.byc_server_enable_auto_session_logout:
            return False

        if company.byc_server_exclude_admin_from_session_expire and self._is_admin():
            return False

        if company.byc_server_enable_user_specific_session_expire:
            if self.id not in company.byc_server_user_specific_session_expire_users.ids:
                return False
        
        return True

    def _is_within_allowed_time_window(self):
        """
        Checks if current time is within allowed login hours
        Returns True if:
        - No user or public user
        - Time restriction not enabled
        - Current time is within window
        - User is admin and exclusion is enabled
        """
        if not self or not self.id:
            return True
            
        company = self.env.company
        if not company.byc_server_enable_time_window:
            return True
            
        # Check if admin exclusion applies
        if company.byc_server_exclude_admin_from_session_expire and self._is_admin():
            return True
            
        from datetime import datetime
        now = datetime.now()
        current_hour = now.hour + now.minute/60.0
        
        return (current_hour >= company.byc_server_start_time and 
                current_hour <= company.byc_server_end_time)

    @api.model
    def _calculate_session_expiration_deadline(self):
        """
        Calculates the deadline based on the current environment's user.
        """
        current_user = self.env.user
        
        # Guard against no user (e.g., public user on website)
        if not current_user or not current_user.id:
            return False

        # Now call the method that works on a single user record
        if not current_user._should_session_expire():
            return False

        # The field stores the value in HOURS (e.g., 1.5 for 1h 30m)
        delay_hours = self.env.company.byc_server_session_expire_limit
        if delay_hours <= 0:
            return False
        
        # Convert hours to seconds (1 hour = 3600 seconds)
        delay_seconds = delay_hours * 3600
        return time() - delay_seconds

    @api.model
    def _perform_session_termination(self, session):
        """ This method remains unchanged. """
        if session.db and session.uid:
            session.logout(keep_db=True)
        return True

    @api.model
    def _validate_session_lifetime(self):
        """
        Entry point for validation, decorated with @api.model.
        """
        if not http.request:
            return

        # Check time window first
        current_user = self.env.user
        if current_user and current_user.id:
            if not current_user._is_within_allowed_time_window():
                session = http.request.session
                if self._perform_session_termination(session):
                    return SessionExpiredException("Access denied outside allowed time window")

        # Then check session expiration
        deadline = self._calculate_session_expiration_deadline()
        
        if deadline is False:
            return

        session = http.request.session
        expired = False
        path = http.root.session_store.get_session_filename(session.sid)
        try:
            expired = getmtime(path) < deadline
        except OSError:
            _logger.debug("Session file not found, considering it expired.", exc_info=True)
            expired = True

        if expired and self._perform_session_termination(session):
            return SessionExpiredException("Session expired due to inactivity.")
