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
from woocommerce import API
from odoo import api, fields, models, _


class ProductTemplate(models.Model):
    """
    Class for the inherited model product_template. Contains fields and
    methods related to Woocommerce product.
    Methods:
        unlink(self):Supering unlink function for deleting values on all
            instances.
        get_product_graph(self):Method to get product details for product
            graph.
        image_upload(self, product):Method to Upload product image into
            WordPress media to get a public link.
        sync_products(self):Method to sync products into Woocommerce.
    """
    _inherit = 'product.template'
    _description = "Product Template"

    woo_id = fields.Char(string='WooCommerce ID', readonly=True, copy=False,
                         help='Id in WooCommerce')
    instance_id = fields.Many2one('woo.commerce.instance', string='Instance',
                                  readonly=True, copy=False,
                                  help='WooCommerce Instance id.')
    woo_variant_check = fields.Boolean(readonly=True, copy=False,
                                       help='Field to check if the product is variant or not.')
    is_grouped_product = fields.Boolean(string='Is Grouped Product',
                                        help='Check whether the product is grouped product')
    woo_product_values = fields.Char(string='Woo Grouped Product IDS',
                                     help='The WooCommerce Product Ids')
    woo_grouped_var_ids = fields.Many2many('product.template',
                                           'woo_grouped_product_rel', 'woo_id',
                                           'product_id',
                                           compute='_compute_grouped_values',
                                           string='WooCommerce Grouped Products')
    external_url_product = fields.Char(
        string='Url of the WooCommerce Website Product', readonly=True,
        help='Url of the WooCommerce Product in Website')

    @api.depends('woo_product_values')
    def _compute_grouped_values(self):
        """
           Compute and update the 'woo_grouped_var_ids' field based on the
           'woo_product_values'. This method is triggered when the value of
           'woo_product_values' changes.
        """
        if self.woo_product_values:
            # Remove unwanted characters and split the string into a list of
            # values
            woo_ids = [int(woo_id.strip("[]' ")) for woo_id in
                       self.woo_product_values.split(',') if woo_id.strip()]
            # Search for product.template records with matching woo_id
            product_templates = self.env['product.template'].search(
                [('woo_id', 'in', woo_ids)])
            # Update the Many2many field with the found records
            self.woo_grouped_var_ids = [(6, 0, product_templates.ids)]
        else:
            # Clear the Many2many field if woo_product_values is empty
            self.woo_grouped_var_ids = [(5, 0, 0)]

    def unlink(self):
        """
        Supering unlink function for deleting values on all instances.
           :return: Record set of ProductTemplate.
        """
        for product in self:
            if product.woo_id and product.instance_id and product.instance_id.product_delete:
                woo_api = product.instance_id.get_api()
                woo_api.delete("products/" + product.woo_id + "",
                               params={"force": True}).json()
        return super(ProductTemplate, self).unlink()

    @api.model
    def get_product_graph(self):
        """Method to get product details for product graph.
            :return: Returns list of dictionary with product details."""
        woo_products = self.env['product.template'].search(
            [('woo_id', '!=', False)])
        products_details = [{'id': product.id, 'name': product.name,
                             'quantity': product.qty_available,
                             'price': product.list_price} for product in
                            woo_products]
        return products_details

    def image_upload(self, product):
        """
        Method to Upload product image into WordPress media to get a public
        link.
            :param product: Record set of product.
            :return: Returns product image url.
        """
        attachment_id = self.env['ir.attachment'].sudo().search(
            [('res_model', '=', 'product.template'),
             ('res_id', '=', product.id), ('res_field', '=', 'image_1920')])
        product_image_url = False
        if attachment_id:
            attachment_id.write({'public': True})
            base_url = self.env['ir.config_parameter'].sudo().get_param(
                'web.base.url')
            product_image_url = f"{base_url}{attachment_id.image_src}.jpg"
        return product_image_url

    def sync_products(self):
        """
        Method to sync products into Woocommerce.
            :return: Returns window action of model woo_update.
        """
        for product_id in self:
            if product_id.instance_id:
                app = API(
                    url="" + product_id.instance_id.store_url + "/index.php/", # Your store URL
                    consumer_key=product_id.instance_id.consumer_key, # Your consumer key
                    consumer_secret=product_id.instance_id.consumer_secret, # Your consumer secret
                    wp_api=True,  # Enable the WP REST API integration
                    version="wc/v3",  # WooCommerce WP REST API version
                    timeout=500,
                )
                image_url = self.image_upload(product_id)
                val_list = {
                    "name": product_id.name,
                    "regular_price": str(product_id.list_price),
                    "description": product_id.description if product_id.description else "",
                    "sku": product_id.default_code if product_id.default_code else "",
                    'manage_stock': True if product_id.type == 'consu' else False,
                    'stock_quantity': int(product_id.qty_available),
                    "images": [
                        {
                            "src": image_url,
                        }
                    ],
                }
                categories = [{
                    'id': product_id.categ_id.woo_id,
                    'name': product_id.categ_id.name,
                    'slug': product_id.categ_id.name
                }]
                val_list.update({
                    "categories": categories
                })
                app.put(f"products/{product_id.woo_id}", val_list).json()
        return {
            'name': _('Sync Products'),
            'view_mode': 'form',
            'res_model': 'woo.update',
            'view_id': self.env.ref('woo_commerce.woo_update_view_form').id,
            'type': 'ir.actions.act_window',
            'context': {'operation_type': 'products', 'active_ids': self.ids},
            'target': 'new'
        }
