# Copyright 2023 Open Source Integrators
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

{
    "name": "Account Move Line Tag",
    "version": "18.0.1.0.1",
    "category": "Accounting",
    "summary": "Add tags to classify account move line reasons",
    "author": "Open Source Integrators, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/sale-workflow",
    "license": "AGPL-3",
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "views/account_move_views.xml",
    ],
    "maintainers": ["smaciaosi", "dreispt", "ckolobow"],
}
