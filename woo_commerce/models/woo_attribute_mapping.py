# -*- coding: utf-8 -*-
###############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#
#    This program is under the terms of the Odoo Proprietary License v1.0(OPL-1)
#    It is forbidden to publish, distribute, sublicense, or sell copies of the
#    Software or modified copies of the Software.
#
###############################################################################
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class WooAttributeMapping(models.Model):
    """
    Model for mapping Odoo Many2many fields to WooCommerce attributes.
    Allows dynamic configuration of which fields should be exported as
    WooCommerce product attributes.
    """
    _name = 'woo.attribute.mapping'
    _description = 'WooCommerce Attribute Mapping'
    _rec_name = 'woo_attribute_name'
    _order = 'sequence, id'

    sequence = fields.Integer(
        default=10,
        help="Order of attribute export"
    )
    active = fields.Boolean(
        default=True,
        string="Active"
    )
    instance_id = fields.Many2one(
        'woo.commerce.instance',
        string='WooCommerce Instance',
        required=True,
        ondelete='cascade',
        help='The WooCommerce instance this mapping belongs to'
    )

    # Source Odoo field configuration
    source_field_id = fields.Many2one(
        'ir.model.fields',
        string='Source Field',
        required=True,
        ondelete='cascade',
        domain="[('model', '=', 'product.template'), ('ttype', 'in', ['many2many', 'selection'])]",
        help='The field from product.template to export as WooCommerce attribute (Many2many or Selection)'
    )
    source_field_name = fields.Char(
        related='source_field_id.name',
        store=True,
        string='Field Technical Name'
    )
    field_type = fields.Selection(
        related='source_field_id.ttype',
        store=True,
        string='Field Type',
        help='Type of the source field (many2many or selection)'
    )
    target_model = fields.Char(
        related='source_field_id.relation',
        store=True,
        string='Target Model',
        help='The model referenced by the Many2many field (empty for selection fields)'
    )
    display_field = fields.Char(
        string='Display Field',
        default='name',
        help='Field from target model to use as attribute value (only for Many2many fields)'
    )

    # WooCommerce attribute configuration
    woo_attribute_name = fields.Char(
        string='WooCommerce Attribute Name',
        required=True,
        help='Name of the attribute as it will appear in WooCommerce'
    )
    woo_attribute_slug = fields.Char(
        string='Attribute Slug',
        compute='_compute_slug',
        store=True,
        help='URL-friendly slug for the attribute'
    )
    woo_attribute_id = fields.Integer(
        string='WooCommerce Attribute ID',
        readonly=True,
        copy=False,
        help='ID of the attribute in WooCommerce (set after export)'
    )

    # Export options
    visible_on_product = fields.Boolean(
        default=True,
        string='Visible on Product Page',
        help='Whether the attribute is visible on the product page in WooCommerce'
    )

    _sql_constraints = [
        ('unique_field_per_instance',
         'UNIQUE(instance_id, source_field_id)',
         'Each field can only be mapped once per instance'),
        ('unique_woo_name_per_instance',
         'UNIQUE(instance_id, woo_attribute_name)',
         'Attribute name must be unique per instance'),
    ]

    @api.depends('woo_attribute_name')
    def _compute_slug(self):
        """Generate a URL-friendly slug from the attribute name using Odoo's native slugify."""
        slugify = self.env['ir.http']._slugify
        for record in self:
            if record.woo_attribute_name:
                record.woo_attribute_slug = slugify(record.woo_attribute_name)
            else:
                record.woo_attribute_slug = False

    @api.constrains('source_field_id', 'display_field', 'field_type')
    def _check_display_field_exists(self):
        """Validate that the display field exists on the target model (only for many2many)."""
        for record in self:
            # Only validate for many2many fields
            if record.field_type == 'many2many' and record.target_model and record.display_field:
                try:
                    target_model_obj = self.env[record.target_model]
                    if record.display_field not in target_model_obj._fields:
                        raise ValidationError(
                            _("The display field '%s' does not exist on model '%s'") %
                            (record.display_field, record.target_model)
                        )
                except KeyError:
                    raise ValidationError(
                        _("The target model '%s' does not exist") % record.target_model
                    )

    def get_attribute_values_for_product(self, product):
        """
        Extract attribute values from a product based on this mapping.
        Supports both many2many and selection field types.
        :param product: product.template record
        :return: list of string values
        """
        self.ensure_one()
        if not self.source_field_name:
            return []

        field_value = getattr(product, self.source_field_name, False)
        if not field_value:
            return []

        if self.field_type == 'selection':
            # For selection fields: return the label of the selected value
            field_obj = product._fields.get(self.source_field_name)
            if field_obj:
                selection_list = field_obj.selection
                if callable(selection_list):
                    selection_list = selection_list(product)
                for key, label in selection_list:
                    if key == field_value:
                        return [label]
            return [str(field_value)]
        else:
            # For many2many fields: return display field values
            values = []
            for record in field_value:
                display_value = getattr(record, self.display_field, False)
                if display_value:
                    values.append(str(display_value))
            return values

    def reset_woo_attribute_id(self):
        """Reset WooCommerce attribute ID to allow re-export."""
        self.write({'woo_attribute_id': False})
