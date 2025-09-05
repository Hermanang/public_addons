# -*- coding: utf-8 -*-
from odoo.addons.website_sale.controllers.main import WebsiteSale as WebsiteSaleCheckout


class WebsiteSale(WebsiteSaleCheckout):

    def _get_mandatory_delivery_address_fields(self, country_sudo):

        return {'name', 'phone'}

    def _get_mandatory_billing_address_fields(self, country_sudo):

        return {'name', 'phone'}
