# Copyright 2016-2022 LasLabs Inc.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

{
    "name": "Optical Clinic Solutions",
    "summary": "",
    "version": "18.0.1.0.1",
    "category": "Discuss",
    "website": "https://github.com/OCA/social",
    "author": "brain-tec AG, LasLabs, Adhoc SA, Odoo Community Association (OCA)",
    "license": "LGPL-3",
    "application": False,
    "installable": True,
    "depends": ["sale_management", "contacts"],
    "data": [
        "security/ir.model.access.csv",

        "report/ir_actions_report_templates.xml",
        "report/ir_actions_report.xml",

        "data/ir_sequence_data.xml",
        "data/partner_category_data.xml",
        "views/prescription_views.xml",
        "views/res_partner.xml",
        "views/sale_order.xml",
        "views/product_template.xml",
        "views/account_move_line.xml",
        "views/product_frame_usage_views.xml",
        "views/product_lens_type_views.xml",
        "views/product_lens_treatment_views.xml",
        "views/product_frame_material_views.xml",
    ],
    "images": ["static/description/icon.png"],
}
