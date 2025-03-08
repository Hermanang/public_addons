# Copyright 2014 Camptocamp, Akretion, Numérigraphe
# Copyright 2016 Sodexis
# Copyright 2019 Sergio Díaz <sergiodm.1989@gmail.com>
# Copyright 2020 Tecnativa - Pedro M. Baeza
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{
    "name": "PoS Stock Available Exclude Location",
    "version": "18.0.1.0.0",
    "depends": ["point_of_sale", "stock_available_immediately_exclude_location"],
    "website": "https://github.com/OCA/stock-logistics-availability",
    "author": "Camptocamp,Sodexis,Odoo Community Association (OCA),Sergio Díaz",
    "license": "AGPL-3",
    "category": "Hidden",
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_stock_available_exclude_location/static/src/components/product_info_popup.xml',
        ]
    },
    "installable": True,
}
