# -*- coding: utf-8 -*-
import logging
from odoo import models
from odoo.http import request, SessionExpiredException

_logger = logging.getLogger(__name__) # <<< LOGGER INITIALIZATION ADDED


class IrHttp(models.AbstractModel):
    _inherit = "ir.http" # Inheriting from the standard Odoo model responsible for HTTP dispatching

    @classmethod
    def _authenticate(cls, endpoint):
        res = super()._authenticate(endpoint=endpoint)
        if (
            request
            and request.session
            and request.session.uid
            and not request.env["res.users"].browse(request.session.uid)._is_public()
        ):
            # First check time window restrictions
            user = request.env.user
            if user and user.id and not user._is_within_allowed_time_window():
                request.session.logout(keep_db=True)
                raise SessionExpiredException("Access denied outside allowed time window")
            
            # Then validate session lifetime
            user._validate_session_lifetime()
        return res
