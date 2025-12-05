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
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NON INFRINGEMENT. IN NO EVENT SHALL
#    THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,DAMAGES OR OTHER
#    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,ARISING
#    FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#    DEALINGS IN THE SOFTWARE.
#
###############################################################################
from odoo import api, fields, models


class ProductPublicCategory(models.Model):
    """
    Class for the inherited model product.public.category. Contains fields
    and method related to Woocommerce product categories (eCommerce).
    Methods:
        get_product_category_graph(self):Method to return  product category
        names and count of products into module dashboard.
    """
    _inherit = 'product.public.category'

    woo_id = fields.Char(string='WooCommerce ID', copy=False, readonly=True,
                         help='Id in WooCommerce')
    instance_id = fields.Many2one('woo.commerce.instance',
                                  copy=False, readonly=True, string='Instance',
                                  help='WooCommerce Instance')

    @api.model
    def get_product_category_graph(self):
        """
        Method to return  product category names and count of products into
        module dashboard.
            :return: Returns dictionary of category names and product count.
        """
        categories = self.env['product.public.category'].search([
            ('woo_id', '!=', False)])
        products_count = [self.env['product.template'].search_count(
            [('public_categ_ids', 'in', [category.id])]) for category in categories]
        return {
            'categories_name': categories.mapped('name'),
            'products_count': products_count
        }
