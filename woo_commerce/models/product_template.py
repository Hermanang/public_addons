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
from odoo import api, fields, models, _, SUPERUSER_ID


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

    def image_upload(self, product, res_field='image_1920', res_id=None):
        """
        Method to Upload product image into WordPress media to get a public
        link.
            :param product: Record set of product.
            :param res_field: Field name for the image (default: 'image_1920')
            :param res_id: ID for product.image records (used for additional images)
            :return: Returns product image url.
        """
        # Utiliser SUPERUSER_ID pour bypasser tous les ACL
        Attachment = self.env['ir.attachment'].with_user(SUPERUSER_ID)

        if res_id:
            # Pour les images supplémentaires (product.image)
            attachment_id = Attachment.search(
                [('res_model', '=', 'product.image'),
                 ('res_id', '=', res_id),
                 ('res_field', '=', res_field)],
                limit=1)
        else:
            # Pour l'image principale (product.template)
            attachment_id = Attachment.search(
                [('res_model', '=', 'product.template'),
                 ('res_id', '=', product.id),
                 ('res_field', '=', res_field)],
                limit=1)

        product_image_url = False
        if attachment_id:
            # Écrire avec SUPERUSER_ID pour garantir les droits
            attachment_id.write({'public': True})
            base_url = self.env['ir.config_parameter'].sudo().get_param(
                'web.base.url')
            product_image_url = f"{base_url}{attachment_id.image_src}.jpg"
        return product_image_url

    def prepare_woo_images(self, product):
        """
        Prépare toutes les images d'un produit pour l'export vers WooCommerce.
        Étape 1 : Vérifie si le produit a des images supplémentaires (product_template_image_ids)
        Étape 2 : Si oui, upload toutes ces images ; sinon, fallback sur image_1920
        Étape 3 : Évite les doublons en vérifiant woo_image_id

            :param product: Record set of product.template
            :return: List of image dictionaries for WooCommerce API
        """
        images_list = []

        # Étape 1 : Vérifier s'il y a des images supplémentaires
        if product.product_template_image_ids:
            # Upload toutes les images de la galerie
            for image_record in product.product_template_image_ids:
                # Étape 4 : Éviter les doublons - vérifier si l'image a déjà un woo_image_id
                if image_record.woo_image_id:
                    # L'image existe déjà sur WooCommerce, utiliser l'ID existant
                    images_list.append({
                        "id": int(image_record.woo_image_id),
                        "name": image_record.name or ""
                    })
                else:
                    # Uploader la nouvelle image
                    image_url = self.image_upload(
                        product,
                        res_field='image_1920',
                        res_id=image_record.id
                    )
                    if image_url:
                        images_list.append({
                            "src": image_url,
                            "name": image_record.name or ""
                        })

        # Étape 2 : Fallback sur image_1920 si aucune image supplémentaire
        elif product.image_1920:
            image_url = self.image_upload(product)
            if image_url:
                images_list.append({
                    "src": image_url,
                    "name": product.name
                })

        return images_list

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
                # Utiliser la nouvelle méthode prepare_woo_images pour gérer toutes les images
                images_list = self.prepare_woo_images(product_id)

                val_list = {
                    "name": product_id.name,
                    "regular_price": str(product_id.list_price),
                    "description": product_id.description if product_id.description else "",
                    "sku": product_id.default_code if product_id.default_code else "",
                    'manage_stock': True if product_id.type == 'consu' else False,
                    'stock_quantity': int(product_id.qty_available),
                }

                # Ajouter les images seulement si la liste n'est pas vide
                if images_list:
                    val_list["images"] = images_list

                # Build categories list from public_categ_ids (Many2many)
                categories = []
                seen_ids = set()
                for pub_categ in product_id.public_categ_ids:
                    # Add the category and its parent hierarchy
                    current_cat = pub_categ
                    while current_cat:
                        if current_cat.id not in seen_ids and current_cat.woo_id:
                            categories.append({
                                'id': current_cat.woo_id,
                                'name': current_cat.name,
                                'slug': current_cat.name
                            })
                            seen_ids.add(current_cat.id)
                        current_cat = current_cat.parent_id
                val_list.update({
                    "categories": categories
                })

                # Envoyer la requête et récupérer la réponse
                response = app.put(f"products/{product_id.woo_id}", val_list).json()

                # Étape 3 : Mettre à jour les woo_image_id après la réponse
                if response.get('images') and product_id.product_template_image_ids:
                    for index, woo_image in enumerate(response['images']):
                        if index < len(product_id.product_template_image_ids):
                            image_record = product_id.product_template_image_ids[index]
                            if not image_record.woo_image_id:
                                image_record.woo_image_id = str(woo_image['id'])

        return {
            'name': _('Sync Products'),
            'view_mode': 'form',
            'res_model': 'woo.update',
            'view_id': self.env.ref('woo_commerce.woo_update_view_form').id,
            'type': 'ir.actions.act_window',
            'context': {'operation_type': 'products', 'active_ids': self.ids},
            'target': 'new'
        }
