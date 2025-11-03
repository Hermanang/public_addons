# -*- coding: utf-8 -*-
###############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Jumana Jabin MP (odoo@cybrosys.com)
#
#    This program is under the terms of the Odoo Proprietary License v1.0(OPL-1)
#    It is forbidden to publish, distribute, sublicense, or sell copies of the
#    Software or modified copies of the Software.
#
#    THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NON INFRINGEMENT. IN NO EVENT SHALL
#    THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,DAMAGES OR OTHER
#    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,ARISING
#    FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#    DEALINGS IN THE SOFTWARE.
#
###############################################################################
from odoo import fields,models


class ProductAttribute(models.Model):
    """
    Class for the inherited model product_attribute. Contains fields
    related to Woocommerce attributes.
    """
    _inherit = 'product.attribute'

    woo_id = fields.Char(string='WooCommerce ID', readonly=True, copy=False,
                         help='Id in WooCommerce')
    instance_id = fields.Many2one('woo.commerce.instance', string='Instance',
                                  readonly=True, copy=False,
                                  help='WooCommerce Instance id')
    slug = fields.Char(string='Slug', help='Slug value of the attribute')

    _sql_constraints = [
        ('unique_slug', 'UNIQUE(slug)', 'The slug must be unique'),
    ]


class ProductAttributeValue(models.Model):
    """
    Class for the inherited model product_attribute_value. Contains fields
    related to Woocommerce attribute values.
    """
    _inherit = 'product.attribute.value'

    woo_id = fields.Char(string='WooCommerce ID', readonly=True, copy=False,
                         help='Id in WooCommerce')
    instance_id = fields.Many2one('woo.commerce.instance', string='Instance',
                                  readonly=True, copy=False,
                                  help='WooCommerce Instance id')
    slug = fields.Char(string='Slug', help='Slug value of the attribute.')

    _sql_constraints = [
        ('unique_slug', 'UNIQUE(slug)', 'The slug must be unique')]
