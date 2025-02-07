# ©  2008-2021 Deltatech
# See README.rst file on addons root folder for license details


from odoo import fields, models


class ProductAttributeGroup(models.Model):
    _name = "product.attribute.group"
    _description = "Attribute Group"

    name = fields.Char()
    attribute_ids = fields.One2many("product.attribute", "group_id")


class ProductAttribute(models.Model):
    _inherit = "product.attribute"

    group_id = fields.Many2one("product.attribute.group")

