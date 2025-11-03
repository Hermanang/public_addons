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
import logging
from odoo import http
from odoo import SUPERUSER_ID
from odoo.http import request
from datetime import datetime
from woocommerce import API

_logger = logging.getLogger(__name__)


class Webhooks(http.Controller):
    """
     Controller handling webhooks for customer creation.
     """
    @http.route('/customers/create', type='http', auth="none", csrf=False)
    def create_customer(self, **kw):
        """
        Handle the customer creation webhook.
        """
        if not kw:
            try:
                response = request.get_json_data()
                _logger.info(
                    "CREATE CUSTOMER WEBHOOK call for this customer: %s",
                    response)
            except Exception as e:
                _logger.error(
                    "Error while processing CUSTOMER CREATE WEBHOOK: %s",
                    str(e))
                return True
            try:
                shop_name = request.httprequest.headers.get(
                    "X-WC-Webhook-Source").rstrip('/')
                instance_id = request.env[
                    "woo.commerce.instance"].sudo().search(
                    [("store_url", "ilike", shop_name)], limit=1)
                self.create_new_customer(response, instance_id)
            except Exception as e:
                request.env['woo.logs'].with_user(SUPERUSER_ID).create({
                    'status': 'failed',
                    'description': f'Failed to Create customer with '
                                   f'woo_id {response.get("id")}. '
                                   f'Error: {str(e)}',
                    'trigger': 'import'
                })
                return {"Message": "Something went wrong"}

    @http.route('/customers/update', type='http', auth="none", csrf=False)
    def update_customer(self, **kw):
        """
        Handle the customer update webhook.
        """
        if not kw:
            try:
                response = request.get_json_data()
                _logger.info(
                    "UPDATE CUSTOMER WEBHOOK call for this customer: %s",
                    response)
            except Exception as e:
                _logger.error(
                    "Error while processing Customer UPDATE WEBHOOK: %s",
                    str(e))
                return True
            try:
                shop_name = request.httprequest.headers.get(
                    "X-WC-Webhook-Source").rstrip('/')
                instance_id = request.env[
                    "woo.commerce.instance"].sudo().search(
                    [("store_url", "ilike", shop_name)], limit=1)
                self.create_or_update_customer(response, instance_id)
            except Exception as e:
                request.env['woo.logs'].with_user(SUPERUSER_ID).create({
                    'status': 'failed',
                    'description': f'Failed to update customer with woo_id {response.get("id")}. Error: {str(e)}',
                    'trigger': 'import'
                })

    def create_or_update_customer(self, rec, instance_id):
        """
        Function to create new customer and update the customer.
            :returns: The customer id.
            :rtype: Int
        """
        if str(rec.get('id')) in request.env['res.partner'].sudo().search(
            [('type', '=', 'contact')]).mapped('woo_id'):
            partner_id = request.env['res.partner'].sudo().search(
                [('type', '=', 'contact'), ('woo_id', '=', rec.get('id'))])
            if partner_id:
                updated_values = {
                    'email': rec.get('email'),
                    'name': f"{rec.get('first_name', '').strip()} {rec.get('last_name', '').strip()}",
                }
                rec['billing'].get('first_name', '').strip()
                partner_id.sudo().write(updated_values)

                if rec.get('billing').get('first_name'):
                    billing_address = {
                        'name': f"{rec['billing'].get('first_name', '').strip()} "
                                f"{rec['billing'].get('last_name', '').strip()}",
                        'phone': rec['billing'].get('phone') or '',
                        'street': rec['billing'].get('address_1') or '',
                        'street2': rec['billing'].get('address_2') or '',
                        'city': rec['billing'].get('city') or '',
                        'zip': rec['billing'].get('postcode') or '',
                        'country_id': request.env[
                            'res.country'].sudo().search(
                            [('code', '=', rec['billing']['country'])]).id,
                        'state_id': request.env[
                            'res.country.state'].sudo().search(
                            [('code', '=', rec['billing']['state']),
                             ('country_id', '=',
                              rec['billing']['country'])]).id if
                        rec['billing']['country'] else False,
                        'type': 'invoice',
                        'instance_id': instance_id.id,
                        'parent_id': partner_id.id,
                    }
                    billing_partner = request.env['res.partner'].sudo().search(
                        [('type', '=', 'invoice'),
                         ('parent_id', '=', partner_id.id)])
                    if billing_partner:
                        billing_partner.sudo().write(billing_address)
                    else:
                        request.env['res.partner'].with_user(
                            SUPERUSER_ID).create(billing_address)
                if rec.get('shipping').get('first_name'):
                    delivery_address = {
                        'name': f"{rec['shipping'].get('first_name', '').strip()} "
                                f"{rec['shipping'].get('last_name', '').strip()}",
                        'phone': rec['shipping'].get('phone') or '',
                        'street': rec['shipping'].get('address_1') or '',
                        'street2': rec['shipping'].get('address_2') or '',
                        'city': rec['shipping'].get('city') or '',
                        'zip': rec['shipping'].get('postcode') or '',
                        'country_id': request.env[
                            'res.country'].sudo().search(
                            [('code', '=', rec['shipping']['country'])]).id,
                        'state_id': request.env[
                            'res.country.state'].sudo().search(
                            [('code', '=', rec['shipping']['state']),
                             ('country_id', '=',
                              rec['shipping']['country'])]).id if
                        rec['shipping']['country'] else False,
                        'type': 'delivery',
                        'instance_id': instance_id.id,
                        'parent_id': partner_id.id,
                    }
                    delivery_partner = request.env['res.partner'].sudo().search(
                        [('type', '=', 'delivery'),
                         ('parent_id', '=', partner_id.id)])
                    if delivery_partner:
                        delivery_partner.sudo().write(delivery_address)
                    else:
                        request.env['res.partner'].with_user(
                            SUPERUSER_ID).create(delivery_address)

                request.env['woo.logs'].with_user(SUPERUSER_ID).create({
                    'status': 'success',
                    'description': f'Customer with woo_id {rec.get("id")} updated successfully from WEBHOOK',
                    'trigger': 'import'
                })
        else:
            self.create_new_customer(rec, instance_id)

    def create_new_customer(self, rec, instance_id):
        """
        Function to Create new customer
        """
        val = request.env['woo.operation'].sudo().prepare_customer_vals(rec)
        mail_list = request.env['res.partner'].sudo().search(
            [('type', '=', 'contact')]).mapped('email')
        partner_id = False
        if val.get('email') not in mail_list:
            val['instance_id'] = instance_id.id if instance_id.id else False
            _logger.info(
                "*************** Creating the partner ****************")
            partner_id = request.env['res.partner'].with_user(
                SUPERUSER_ID).create(val)
            request.env['woo.logs'].with_user(SUPERUSER_ID).create({
                'status': 'success',
                'description': f'Partner with email {val.get("email")} created successfully from WEBHOOK',
                'trigger': 'import'
            })
            _logger.info(
                "*************** Partner Creation done ***************")
        return partner_id

    @http.route('/customer/delete', type='http', auth="none", csrf=False)
    def delete_customer(self, **kw):
        """
        Handle the customer deletion webhook.
        """
        if not kw:
            try:
                response = request.get_json_data()
                _logger.info(
                    "DELETE CUSTOMER WEBHOOK call for this customer: %s",
                    response)
            except Exception as e:
                _logger.error("Error getting JSON data from webhook: %s", e)
                return True
            try:
                customer_id = request.env['res.partner'].with_user(
                    SUPERUSER_ID).search([('type', '=', 'contact'),
                                          ('woo_id', '=', response.get('id'))])
                if customer_id:
                    try:
                        customer_id.sudo().write({
                            'active': False,
                        })
                        _logger.info(
                            "Customer with Woo ID %s deactivated successfully.",
                            response.get('id'))
                    except Exception as e:
                        _logger.error(
                            "Error deactivating customer with Woo ID %s: %s",
                            response.get('id'), e)
                        request.env['woo.logs'].sudo().create({
                            'status': 'failed',
                            'trigger': 'delete_customer',
                            'description': f"Customer with Woo ID {response.get('id')} deletion failed: {e}",
                        })
            except Exception as e:
                request.env['woo.logs'].sudo().create({
                    'status': 'failed',
                    'trigger': 'delete_customer',
                    'description': f"Customer deletion failed: {e}",
                })

    @http.route('/product/create', type='http', auth="none", csrf=False)
    def create_product(self, **kw):
        """
        Handle the Product creation webhook.
        """
        if not kw:
            try:
                # Response of Product
                response = request.get_json_data()
                _logger.info("PRODUCT CREATE WEBHOOK call for this product: %s",
                             response)
            except Exception as e:
                _logger.error(
                    "Error while processing PRODUCT CREATE WEBHOOK: %s", str(e))
                return True
            try:
                # Retrieve the store name from the request headers
                shop_name = request.httprequest.headers.get(
                    "X-WC-Webhook-Source").rstrip('/')

                # Search for the corresponding WooCommerce instance based on the store name
                instance_id = request.env[
                    "woo.commerce.instance"].sudo().search(
                    [("store_url", "ilike", shop_name)], limit=1)

                woo_ids = request.env['product.template'].sudo().search([]).mapped('woo_id')
                # Continue with product creation only if it's not already in Odoo
                if str(response.get('id')) not in woo_ids:
                    if response.get('type') in ['simple', 'variable', 'bundle',
                                                'grouped', 'external']:

                        # Product With No Variables
                        if response.get('type') in ['simple', 'bundle',
                                                    'grouped', 'external']:
                            # Preparing the Product Values
                            val_list = request.env[
                                'woo.operation'].sudo().prepare_product_vals(
                                response, instance_id)
                            val_list['woo_variant_check'] = True
                            # Updating the val_list
                            val_list[
                                'instance_id'] = instance_id.id if instance_id else False
                            val_list[
                                'company_id'] = instance_id.company_id.id if instance_id else False
                            val_list[
                                'currency_id'] = instance_id.currency if instance_id else False
                            # Getting the image
                            image = request.env[
                                'woo.operation'].sudo().get_product_image(
                                response)
                            if image.get('main_image'):
                                val_list.update(image.get('main_image'))
                            if image.get('product_template_image_ids'):
                                val_list[
                                    'product_template_image_ids'] = image.get(
                                    'product_template_image_ids')
                            # Handle virtual products
                            if response.get('virtual'):
                                val_list['detailed_type'] = 'service'
                            if response.get('type') == 'grouped':
                                val_list['detailed_type'] = 'consu'
                                val_list['is_grouped_product'] = True
                                grouped_product_ids = response.get(
                                    'grouped_products', [])
                                val_list[
                                    'woo_product_values'] = grouped_product_ids
                                # external products
                            if response.get('type') == 'external':
                                val_list['detailed_type'] = 'consu'
                            val_list['woo_variant_check'] = True

                            # Splitting the Response of Product Type
                            _logger.info(
                                "*************** CREATING NEW SIMPLE PRODUCT ***************")
                            # Create the new simple product
                            product_id = request.env[
                                'product.template'].with_user(
                                SUPERUSER_ID).create(val_list)
                            _logger.info(
                                "*************** CREATION OF NEW SIMPLE PRODUCT DONE ***************")

                            # If product is created, set stock information
                            if product_id:
                                if response.get(
                                        'manage_stock') and response.get(
                                        'stock_quantity') >= 1:
                                    # add stock for the product(variant)
                                    variant = request.env[
                                        'product.product'].with_user(
                                        SUPERUSER_ID).search(
                                        [('product_tmpl_id', '=',
                                          product_id.id)],  limit=1)
                                    request.env['woo.operation'].with_user(
                                        SUPERUSER_ID).create_stock_vals(
                                        variant, response)
                                _logger.info(
                                    "*************** CREATING NEW SIMPLE PRODUCT COMPLETED***************")
                            # Product With Variables
                        elif response.get('type') == 'variable':
                            # Prepare the Product Values
                            val_list = request.env[
                                'woo.operation'].sudo().prepare_product_vals(
                                response, instance_id)
                            # Updating the Val_list
                            val_list[
                                'instance_id'] = instance_id.id if instance_id else False
                            val_list[
                                'company_id'] = instance_id.company_id.id if instance_id else False
                            val_list[
                                'currency_id'] = instance_id.currency if instance_id else False
                            # Image of the Product
                            image = request.env[
                                'woo.operation'].sudo().get_product_image(
                                response)
                            if image.get('main_image'):
                                val_list.update(image.get('main_image'))
                            if image.get('product_template_image_ids'):
                                val_list[
                                    'product_template_image_ids'] = image.get(
                                    'product_template_image_ids')
                            # Getting all the Variants.
                            app = request.env['woo.operation'].sudo().search(
                                []).get_api()
                            response_variants = app.get(
                                "products/%s/variations" % (response.get("id")))
                            variants = response_variants.json()
                            # Get all variants for the variable product
                            if variants:
                                # Get attribute line values
                                attribute_line_ids = request.env[
                                    'woo.operation'].with_user(
                                    SUPERUSER_ID).get_attribute_line_vals(
                                    variants)
                                # Update val_list with attribute line information
                                val_list[
                                    'attribute_line_ids'] = attribute_line_ids
                                # Update variant values
                                variant_vals = request.env[
                                    'woo.operation'].with_user(
                                    SUPERUSER_ID).update_variants(variants)
                                val_list['woo_variant_check'] = True
                                variant_stock_vals = request.env[
                                    'woo.operation'].with_user(
                                    SUPERUSER_ID).update_variant_stock_vals(
                                    variants)
                                _logger.info(
                                    "*************** Getting NEW Variable PRODUCT ***************")
                                product_id = request.env[
                                    'product.template'].with_user(
                                    SUPERUSER_ID).create(val_list)
                                request.env['woo.logs'].with_user(
                                    SUPERUSER_ID).create({
                                    'status': 'success',
                                    'description': f'Product with woo_id {response.get("id")} created successfully.',
                                    'trigger': 'import'
                                })
                                _logger.info(
                                    "*************** CREATING NEW Vairable PRODUCT ***************")
                                if product_id:
                                    product = request.env[
                                        'product.template'].sudo().browse(
                                        product_id.id)
                                    if product:
                                        # Iterate through variant values
                                        for rec in variant_vals:
                                            # Check if the variant has combinations
                                            if rec['combination']:
                                                attr_ids = [attr_id for attr_id
                                                            in rec[
                                                                'combination'].keys()]
                                                attr_value_ids = [
                                                    attr_value_id[0]
                                                    for attr_value_id in
                                                    rec['combination'].values()]
                                                # Search for product template attribute values
                                                domain = [
                                                    ('product_tmpl_id', '=',
                                                     product.id),
                                                    ('attribute_id', 'in',
                                                     attr_ids), (
                                                        'product_attribute_value_id',
                                                        'in', attr_value_ids)]
                                                product_templ_attr_value = \
                                                    request.env[
                                                        'product.template.attribute.value'].sudo().search(
                                                        domain)
                                                product_variant = product.product_variant_ids.filtered(
                                                    lambda
                                                        variant: variant.product_template_variant_value_ids.ids == product_templ_attr_value.ids)
                                                if product_variant:
                                                    # Remove the 'combination' key from variant values
                                                    del rec['combination']
                                                    # Update the product variant
                                                    product_variant[
                                                        0].sudo().write(rec)
                                    # Create stock for variants
                                    if variant_stock_vals:
                                        request.env[
                                            'woo.operation'].with_user(
                                            SUPERUSER_ID).create_stock_variants(
                                            variant_stock_vals, product)
                                        _logger.info(
                                            "*************** CREATING NEW Variable PRODUCT COMPLETED***************")

            except Exception as e:
                request.env['woo.logs'].with_user(SUPERUSER_ID).create({
                    'status': 'failed',
                    'description': f'Failed to process PRODUCT CREATE WEBHOOK. Error: {str(e)}',
                    'trigger': 'import'
                })
                return {"Message": "Something went wrong"}

    @http.route('/product/update', type='http', auth="none", csrf=False)
    def update_product(self, **kw):
        """
        Handle the product update webhook.
        """
        if not kw:
            try:
                # Response of Product
                response = request.get_json_data()
                _logger.info("PRODUCT UPDATE WEBHOOK call for this product: %s",
                             response)
            except Exception as e:
                _logger.error(
                    "Error while processing PRODUCT CREATE WEBHOOK: %s", str(e))
                return True
            shop_name = request.httprequest.headers.get(
                "X-WC-Webhook-Source").rstrip('/')
            instance_id = request.env["woo.commerce.instance"].sudo().search(
                [("store_url", "ilike", shop_name)], limit=1)
            woo_ids = request.env['product.template'].sudo().search([]).mapped('woo_id')

            if str(response.get('id')) in woo_ids:
                product_id = request.env['product.template'].sudo().search(
                    [('woo_id', '=', response.get('id'))])
                if product_id:
                    if response.get('type') in ['simple', 'bundle']:
                        # Update the existing product
                        _logger.info(
                            "*************** Updating Product ***************")
                        # Prepare the Product Values
                        val_list = request.env[
                            'woo.operation'].sudo().prepare_product_vals(
                            response, instance_id)
                        # Updating the Val_list
                        val_list[
                            'instance_id'] = instance_id.id if instance_id else False
                        val_list[
                            'company_id'] = instance_id.company_id.id if instance_id else False
                        val_list[
                            'currency_id'] = instance_id.currency if instance_id else False
                        # Image of the Product
                        image = request.env[
                            'woo.operation'].sudo().get_product_image(response)
                        if image.get('main_image'):
                            val_list.update(image.get('main_image'))
                        if image.get('product_template_image_ids'):
                            val_list['product_template_image_ids'] = image.get(
                                'product_template_image_ids')
                        # Update the Product Category
                        categories_value = response.get('categories')
                        if categories_value:
                            category_woo_id = categories_value[0].get('id')
                            category_id = request.env[
                                'product.category'].sudo().search(
                                [('woo_id', '=', category_woo_id)], limit=1)
                            if category_id:
                                val_list['categ_id'] = category_id.id
                        # Update the product
                        product_id.sudo().write(val_list)
                        _logger.info(
                            "************** Updating Product Values **************")
                        if response.get('manage_stock') and response.get(
                                'stock_quantity') >= 1:
                            # add stock for the product(simple)
                            variant = request.env[
                                'product.product'].with_user(
                                SUPERUSER_ID).search(
                                [('product_tmpl_id', '=', product_id.id)],
                                limit=1)
                            existing_stock = request.env[
                                'stock.quant'].sudo().search([
                                ('product_id', '=', variant.id)])
                            if existing_stock:
                                existing_stock.sudo().unlink()
                            request.env['woo.operation'].with_user(
                                SUPERUSER_ID).create_stock_vals(
                                variant, response)
                    # Product With Variables
                    elif response.get('type') == 'variable':
                        _logger.info(
                            "*************** Updating Variable Product ***************")
                        # Prepare the Product Values
                        val_list = request.env[
                            'woo.operation'].sudo().prepare_product_vals(
                            response, instance_id)
                        # Updating the Val_list
                        val_list[
                            'instance_id'] = instance_id.id if instance_id else False
                        val_list[
                            'company_id'] = instance_id.company_id.id if instance_id else False
                        val_list[
                            'currency_id'] = instance_id.currency if instance_id else False
                        # Image of the Product
                        image = request.env[
                            'woo.operation'].sudo().get_product_image(response)
                        if image.get('main_image'):
                            val_list.update(image.get('main_image'))
                        if image.get('product_template_image_ids'):
                            val_list['product_template_image_ids'] = image.get(
                                'product_template_image_ids')
                        app = request.env['woo.operation'].sudo().search(
                            []).get_api()
                        response_variants = app.get(
                            "products/%s/variations" % (response.get("id")))
                        variants = response_variants.json()
                        # Get all variants for the variable product
                        if variants:
                            # Delete Existing Attribute
                            attribute_lines = product_id.attribute_line_ids
                            attribute_lines.unlink()
                            # Get attribute line values
                            attribute_line_ids = request.env[
                                'woo.operation'].with_user(
                                SUPERUSER_ID).get_attribute_line_vals(
                                variants)
                            # Update val_list with attribute line information
                            val_list['attribute_line_ids'] = attribute_line_ids
                            variant_vals = request.env[
                                'woo.operation'].with_user(
                                SUPERUSER_ID).update_variants(variants)
                            variant_stock_vals = request.env[
                                'woo.operation'].with_user(
                                SUPERUSER_ID).update_variant_stock_vals(
                                variants)
                            product_id.sudo().write(val_list)
                            if product_id:
                                product = request.env[
                                    'product.template'].sudo().browse(
                                    product_id.id)
                                if product:
                                    # Iterate through variant values
                                    for rec in variant_vals:
                                        # Check if the variant has combinations
                                        if rec['combination']:
                                            attr_ids = [attr_id for attr_id in
                                                        rec['combination'].keys()]
                                            attr_value_ids = [attr_value_id[0]
                                                              for attr_value_id
                                                              in rec[
                                                                  'combination'].values()]
                                            # Search for product template attribute values
                                            domain = [('product_tmpl_id', '=',
                                                       product.id),
                                                      ('attribute_id', 'in',
                                                       attr_ids), (
                                                          'product_attribute_value_id',
                                                          'in', attr_value_ids)]
                                            product_templ_attr_value = \
                                                request.env[
                                                    'product.template.attribute.value'].sudo().search(
                                                    domain)
                                            product_variant = product.product_variant_ids.filtered(
                                                lambda
                                                    variant: variant.product_template_variant_value_ids.ids == product_templ_attr_value.ids)
                                            if product_variant:
                                                # Remove the 'combination' key from variant values
                                                del rec['combination']
                                                # Update the product variant
                                                product_variant[0].sudo().write(
                                                    rec)
                                # Create stock for variants
                                if variant_stock_vals:
                                    request.env[
                                        'woo.operation'].with_user(
                                        SUPERUSER_ID).create_stock_variants(
                                        variant_stock_vals, product)
                                    _logger.info(
                                        "*************** Updating Variable PRODUCT COMPLETED***************")

    @http.route('/product/delete', type='http', auth="none", csrf=False)
    def delete_product(self, **kw):
        """
        Handle the product delete webhook.
        """
        if not kw:
            # Response of Product
            if not kw:
                try:
                    response = request.get_json_data()
                    _logger.info(
                        "DELETE Product WEBHOOK call for this Product: %s",
                        response)
                except Exception as e:
                    _logger.error("Error getting JSON data from webhook: %s", e)
                    return True
                try:
                    product_id = request.env['product.template'].with_user(
                        SUPERUSER_ID).search(
                        [('woo_id', '=', response.get('id'))])
                    if product_id:
                        _logger.info(
                            "*************** Deactivating Product ***************")
                        product_id.sudo().write({
                            'active': False,
                        })
                        _logger.info(
                            "************** Deactivating Product Done **************")
                except Exception as e:
                    request.env['woo.logs'].with_user(
                        SUPERUSER_ID).create({
                        'status': 'failed',
                        'description': f'Failed to process DELETE Product WEBHOOK. Error: {str(e)}',
                        'trigger': 'import'
                    })
                    return True

    @http.route('/product/restore', type='http', auth="none", csrf=False)
    def restore_product(self, **kw):
        """
        Handle the product restore webhook.
        """
        if not kw:
            try:
                response = request.get_json_data()
                _logger.info(
                    "DELETE Product WEBHOOK call for this Product: %s",
                    response)
            except Exception as e:
                _logger.error("Error getting JSON data from webhook: %s", e)
                return True
            try:
                product_id = request.env['product.template'].with_user(
                    SUPERUSER_ID).search(
                    [('active', '=', False),
                     ('woo_id', '=', response.get('id'))])
                if product_id and product_id.active is False:
                    _logger.info(
                        "*************** Restore Product ***************")
                    product_id.sudo().write({
                        'active': True,
                    })
                    _logger.info(
                        "************** Restoring Product Done **************")
            except Exception as e:
                request.env['woo.logs'].with_user(
                    SUPERUSER_ID).create({
                    'status': 'failed',
                    'description': f'Failed to process Restore Product WEBHOOK. Error: {str(e)}',
                    'trigger': 'import'
                })
                return True

    def variant_product_tmpl_create(self, product_data, instance_id):
        """
        Handle the creation of variable products from webhook data.
        """
        val_list = request.env[
            'woo.operation'].sudo().prepare_product_vals(
            product_data, instance_id)
        val_list[
            'instance_id'] = instance_id.id if instance_id else False
        val_list[
            'company_id'] = instance_id.company_id.id if instance_id else False
        val_list[
            'currency_id'] = instance_id.currency if instance_id else False
        # Image of the Product
        image = request.env[
            'woo.operation'].sudo().get_product_image(product_data)
        if image.get('main_image'):
            val_list.update(image.get('main_image'))
        if image.get('product_template_image_ids'):
            val_list['product_template_image_ids'] = image.get(
                'product_template_image_ids')
        # Getting all the Variants.
        app = request.env['woo.operation'].sudo().search([]).get_api()
        response_variants = app.get(
            "products/%s/variations" % (product_data.get("id")))
        variants = response_variants.json()
        # Get all variants for the variable product
        if variants:
            # Get attribute line values
            attribute_line_ids = request.env['woo.operation'].with_user(
                SUPERUSER_ID).get_attribute_line_vals(variants)
            # Update val_list with attribute line information
            val_list['attribute_line_ids'] = attribute_line_ids
            # Update variant values
            variant_vals = request.env['woo.operation'].with_user(
                SUPERUSER_ID).update_variants(variants)
            val_list['woo_variant_check'] = True
            variant_stock_vals = request.env['woo.operation'].with_user(
                SUPERUSER_ID).update_variant_stock_vals(variants)
            _logger.info(
                "*************** Getting NEW Vairable PRODUCT ***************")
            product_id = request.env['product.template'].with_user(
                SUPERUSER_ID).create(val_list)
            _logger.info(
                "*************** CREATING NEW Vairable PRODUCT ***************")
            if product_id:
                product = request.env['product.template'].sudo().browse(
                    product_id.id)
                if product:
                    # Iterate through variant values
                    for rec in variant_vals:
                        # Check if the variant has combinations
                        if rec['combination']:
                            attr_ids = [attr_id for attr_id in
                                        rec['combination'].keys()]
                            attr_value_ids = [attr_value_id[0]
                                              for attr_value_id in
                                              rec['combination'].values()]
                            # Search for product template attribute values
                            domain = [('product_tmpl_id', '=', product.id),
                                      ('attribute_id', 'in', attr_ids), (
                                          'product_attribute_value_id',
                                          'in', attr_value_ids)]
                            product_templ_attr_value = \
                                request.env[
                                    'product.template.attribute.value'].sudo().search(
                                    domain)
                            product_variant = product.product_variant_ids.filtered(
                                lambda
                                    variant: variant.product_template_variant_value_ids.ids == product_templ_attr_value.ids)
                            if product_variant:
                                # Remove the 'combination' key from variant values
                                del rec['combination']
                                # Update the product variant
                                product_variant[0].sudo().write(rec)
                # Create stock for variants
                if variant_stock_vals:
                    request.env['woo.operation'].with_user(
                        SUPERUSER_ID).create_stock_variants(
                        variant_stock_vals, product)
                    _logger.info(
                        "*************** CREATING NEW Variable PRODUCT COMPLETED***************")

    def simple_product_create(self, product_data, instance_id):
        """
        Handle the creation of variable products from webhook data.
        """
        # Preparing the Product Values
        val_list = request.env['woo.operation'].sudo().prepare_product_vals(
            product_data, instance_id)
        val_list['woo_variant_check'] = True
        # Updating the val_list
        val_list[
            'instance_id'] = instance_id.id if instance_id else False
        val_list[
            'company_id'] = instance_id.company_id.id if instance_id else False
        val_list[
            'currency_id'] = instance_id.currency if instance_id else False
        # Getting the image
        image = request.env[
            'woo.operation'].sudo().get_product_image(product_data)
        if image.get('main_image'):
            val_list.update(image.get('main_image'))
        if image.get('product_template_image_ids'):
            val_list['product_template_image_ids'] = image.get(
                'product_template_image_ids')
        # Handle virtual products
        if product_data.get('virtual'):
            val_list['detailed_type'] = 'service'
        # grouped products
        if product_data.get('type') == 'grouped':
            val_list['detailed_type'] = 'consu'
            val_list['is_grouped_product'] = True
            grouped_product_ids = product_data.get('grouped_products', [])
            val_list['woo_product_values'] = grouped_product_ids
        # external products
        if product_data.get('type') == 'external':
            val_list['detailed_type'] = 'consu'

            # Splitting the Response of Product Type
            _logger.info(
                "*************** CREATING NEW SIMPLE PRODUCT ***************")
        # Create the new simple product
        product_id = request.env['product.template'].with_user(
            SUPERUSER_ID).create(val_list)
        _logger.info(
            "*************** CREATION OF NEW SIMPLE PRODUCT DONE ***************")
        # If product is created, set stock information
        if product_id:
            #CODE NEED TO BE ADDED
            if product_data.get('manage_stock') and product_data.get(
                    'stock_quantity') >= 1:
                # add stock for the product(variant)
                variant = request.env['product.product'].with_user(
                    SUPERUSER_ID).search(
                    [('product_tmpl_id', '=', product_id.id)],  limit=1)
                request.env['woo.operation'].with_user(
                    SUPERUSER_ID).create_stock_vals(variant, product_data)
            _logger.info(
                "*************** CREATING NEW SIMPLE PRODUCT COMPLETED***************")

    def get_api(self, instance_id):
        """
        It returns the API object for operations
        """
        return API(
            url="" + instance_id.store_url + "/index.php/",  # Your store URL
            consumer_key=instance_id.consumer_key,  # Your consumer key
            consumer_secret=instance_id.consumer_secret,  # Your consumer secret
            wp_api=True,  # Enable the WP REST API integration
            version="wc/v3",  # WooCommerce WP REST API version
            timeout=500,
        )

    def get_partner_for_single_order(self, data,customer_data, instance_id):
        """
        Method to fetch or create a partner for a single WooCommerce order.
        :param data: Dictionary of WooCommerce order data.
        :param instance_id: Record of the WooCommerce instance.
        :returns: The ID of the partner.
        """ 
        app = self.get_api(instance_id)
        partners = request.env['res.partner'].sudo().search(
            [('instance_id', '=', instance_id.id)])
        if data.get('customer_id'):
            # Fetch partner using customer_id
            partner = partners.filtered(
                lambda x: x.woo_id == str(data.get('customer_id')))
            if partner:
                return partner.id
            else:
                if customer_data:
                    # Create a new customer in Odoo
                    partner_id = (request.env['woo.operation'].sudo()
                                  .create_new_customer(customer_data,instance_id))
                    if partner_id:
                        request.env['woo.logs'].sudo().create({
                            'status': 'success',
                            'trigger': 'import',
                            'description': f'Customer for order ID {data.get("id")} created successfully.',
                        })
                        return partner_id
        else:
            # No customer_id, fallback to billing/shipping address
            address_data = {}
            if request.env['woo.operation'].sudo().has_at_least_one_value(data.get('billing', {})):
                address_data = data['billing']
            elif request.env['woo.operation'].sudo().has_at_least_one_value(data.get('shipping', {})):
                address_data = data['shipping']

            if address_data:
                # Build the name for the partner
                name = f'{address_data.get("first_name", "")} {address_data.get("last_name", "")}'.strip()
                if not name:
                    # Use a default guest user if no name is provided
                    guest_partner = request.env.ref(
                        'woo_commerce.woocommerce_guest').with_user(
                                SUPERUSER_ID)
                    return guest_partner.id if guest_partner else False

                # Check if an email match exists
                if data.get('email') and data['email'] in partners.mapped(
                        'email'):
                    request.env['woo.logs'].sudo().create({
                        'status': 'error',
                        'trigger': 'import',
                        'description': f'Email ID conflict for order ID {data.get("id")}.',
                    })
                    return False

                # Prepare customer data for creation
                partner_data = request.env['woo.operation'].sudo().prepare_customer_vals(address_data)
                if partner_data:
                    partner_data['instance_id'] = instance_id.id
                    partner_id = request.env['res.partner'].sudo().create(partner_data)
                    if partner_id:
                        # Create a billing address for the new partner
                        billing_address_data = {
                            'name':partner_id.name,
                            'parent_id': partner_id.id,
                            'type': 'invoice',
                            'street': address_data.get('address_1'),
                            'street2': address_data.get('address_2'),
                            'phone': address_data.get('phone'),
                            'city': address_data.get('city'),
                            'zip': address_data.get('postcode'),
                            'state_id': request.env['res.country.state'].sudo().search([
                                ('code', '=', address_data.get('state')),
                                ('country_id.code', '=',
                                 address_data.get('country'))
                            ], limit=1).id if address_data.get(
                                'state') and address_data.get(
                                'country') else False,
                            'country_id': request.env['res.country'].sudo().search([
                                ('code', '=', address_data.get('country'))
                            ], limit=1).id if address_data.get(
                                'country') else False,
                        }
                        request.env['res.partner'].sudo().create(billing_address_data)

                        if request.env['woo.operation'].sudo().has_at_least_one_value(data['shipping']):
                            delivery_address = {
                                'name': partner_id.name,
                                'company_id': request.env.company.id if request.env.company else False,
                                'phone': data['shipping']['phone'] if
                                data['shipping'][
                                    'phone'] else False,
                                'street': data['shipping'][
                                    'address_1'] if
                                data['shipping'][
                                    'address_1'] else False,
                                'street2': data['shipping'][
                                    'address_2'] if
                                data['shipping'][
                                    'address_2'] else False,
                                'city': data['shipping']['city'] if
                                data['shipping'][
                                    'city'] else False,
                                'zip': data['shipping']['postcode'] if
                                data['shipping'][
                                    'postcode'] else False,
                                'state_id': request.env[
                                    'res.country.state'].sudo().search(
                                    [('code', '=',
                                      data['shipping']['state']), (
                                         'country_id', '=',
                                         data['shipping'][
                                             'country'])]).id if
                                data['shipping']['country'] else False,
                                'country_id': request.env[
                                    'res.country'].sudo().search(
                                    [('code', '=', data['shipping'][
                                        'country'])]).id if
                                data['shipping']['country'] else False,
                                'type': 'delivery',
                                'parent_id': partner_id.id,
                            }
                            request.env['res.partner'].sudo().create(
                                delivery_address)

                        request.env['woo.logs'].sudo().create({
                            'status': 'success',
                            'trigger': 'import',
                            'description': f'Customer for order ID {data.get("id")} created successfully.',
                        })
                        return partner_id.id
            else:
                # Assign to a default guest partner
                guest_user = request.env.ref('woo_commerce.woocommerce_guest').with_user(
                                SUPERUSER_ID)
                if guest_user:
                    request.env['woo.logs'].sudo().create({
                        'status': 'success',
                        'trigger': 'import',
                        'description': f'Default guest customer assigned to order ID {data.get("id")}.',
                    })
                    return guest_user.id
        return False

    @http.route('/order/create', type='http', auth="none", csrf=False)
    def create_order(self, **kw):
        """
        Handle the order creation webhook.
        """
        if not kw:
            # Retrieve the JSON data from the request
            response = request.get_json_data()
            _logger.info("CREATE WEBHOOK call for order: %s", response)
            try:
                shop_name = request.httprequest.headers.get(
                    "X-WC-Webhook-Source").rstrip('/')
                instance_id = request.env[
                    "woo.commerce.instance"].sudo().search(
                    [("store_url", "ilike", shop_name)], limit=1)
                # Initialize WooCommerce API connection
                app = self.get_api(instance_id)
                # Check if the order with the given ID already exists in Odoo
                woo_ids = request.env['sale.order'].sudo().search([]).mapped('woo_id')
                # Continue with order creation only if it's not already in Odoo
                if str(response.get('id')) not in woo_ids:
                    # Search for an existing partner based on WooCommerce customer ID
                    exist_partner = request.env['res.partner'].sudo().search(
                        [('type', '=', 'contact'),
                         ('woo_id', '=', str(response.get('customer_id'))),
                         ('instance_id', '=', instance_id.id)])
                    partner = ''

                    # Check if the partner exists, otherwise create a new one
                    if exist_partner:
                        partner = exist_partner.id
                    else:
                        # Check if the order is associated with a no user
                        app = self.get_api(instance_id)
                        customer_data = app.get(
                            'customers/%s' % response.get('customer_id'),
                            params={
                                'per_page': 100, 'page': 1}).json()

                        if customer_data:
                            # creating a new partner
                            partner = (self.get_partner_for_single_order
                                       (response,customer_data,instance_id))

                    # Extract order creation date from the response
                    order_create_date = response.get('date_created')
                    date_time_obj = datetime.strptime(order_create_date,
                                                      '%Y-%m-%dT%H:%M:%S')


                    # Initialize state values for the sale order
                    state = 'draft'
                    woo_state = 'draft'

                    # Map WooCommerce order status to Odoo sale order states
                    if response.get('status') == 'pending':
                        state = 'draft'
                        woo_state = 'pending_payment'
                    elif response.get('status') == 'processing':
                        state = 'draft'
                        woo_state = 'processing'
                    elif response.get('status') == 'on-hold':
                        state = 'sale'
                        woo_state = 'on_hold'
                    elif response.get('status') == 'completed':
                        state = 'sale'
                        woo_state = 'completed'
                    elif response.get('status') == 'cancelled':
                        state = 'cancel'
                        woo_state = 'cancelled'
                    elif response.get('status') == 'refunded':
                        state = 'sale'
                        woo_state = 'refunded'
                    elif response.get('status') == 'failed':
                        state = 'cancel'
                        woo_state = 'failed'
                    elif response.get('status') == 'draft':
                        state = 'draft'
                        woo_state = 'draft'

                    # Prepare the values for creating the sale order
                    val_list = {
                        'partner_id': partner,
                        'date_order': date_time_obj, 'woo_id': response.get('id'),
                        'instance_id': instance_id.id if instance_id else False,
                        'woo_order_key': response.get('order_key'), 'state': state,
                        'woo_order_status': woo_state,
                        'company_id': instance_id.company_id.id if instance_id else False,
                        'currency_id': instance_id.currency if instance_id else False
                    }
                    orderline = []  # List to store order lines
                    # Process line items from the response
                    for line_item in response.get('line_items'):
                        woo_tax = []
                        for tax in line_item['taxes']:
                            woo_tax.append(str(tax['id']))
                        # Search for tax IDs in Odoo based on WooCommerce tax IDs
                        tax_id = request.env['account.tax'].sudo().search(
                            []).filtered(lambda r: r.woo_id in woo_tax)

                        main_product = request.env[
                            'product.template'].sudo().search([]).filtered(
                            lambda r: r.woo_id == str(line_item['product_id']))
                        if main_product:
                            main_product = main_product[0]
                            # Check if there are multiple variants for the main product
                            if len(main_product.product_variant_ids) > 1:
                                product = request.env[
                                    'product.product'].sudo().search([]).filtered(
                                    lambda r: r.woo_var_id == str(
                                        line_item['variation_id']))
                                if product:
                                    product = product[0]
                            else:
                                # Use the main product if there is only one variant
                                product = main_product.product_variant_ids[0]
                            if product:
                                if response.get('status') == 'refunded':
                                    # For refunded products, set the price to 0
                                    val = {
                                        'name': product.name,
                                        'product_id': product.id,
                                        'price_unit': 0.0, # Set price to 0 for refunded products
                                        'product_uom_qty': line_item['quantity'],
                                        'tax_id': tax_id.ids,
                                        'customer_lead': 1,
                                    }
                                    orderline.append((0, 0, val))
                                elif response.get('coupon_lines'):
                                    # For products with coupon lines, set the price without discounts
                                    val = {
                                        'name': product.name,
                                        'product_id': product.id,
                                        'product_uom_qty': line_item['quantity'],
                                        'tax_id': tax_id.ids,
                                        'customer_lead': 1,
                                    }
                                    orderline.append((0, 0, val))
                                else:
                                    # For other products, set the price from the line item
                                    val = {
                                        'name': product.name,
                                        'product_id': product.id,
                                        'price_unit': line_item['price'],
                                        'product_uom_qty': line_item['quantity'],
                                        'tax_id': tax_id.ids,
                                        'customer_lead': 1,
                                    }
                                    orderline.append((0, 0, val))
                                if orderline:
                                    val_list['order_line'] = orderline
                        else:
                            # Create a new product if the main product doesn't exist
                            products_data = app.get(
                                'products/%s' % line_item['product_id'],
                                params={'per_page': 100, 'page': 1}).json()
                            if products_data.get('type') in ['simple',
                                                             'variable',
                                                             'bundle',
                                                             'grouped',
                                                             'external']:
                                # Currently including these woocommerce product types only
                                product = False
                                if products_data.get('type') in ['simple',
                                                                 'bundle']:
                                    # no need to create variants for these products, so we can use a separate function
                                    # Create a simple product without variants
                                    simple_product = self.simple_product_create(
                                        products_data, instance_id)
                                    if simple_product:
                                        if type(simple_product) == int:
                                            product = request.env[
                                                'product.template'].sudo().browse(
                                                simple_product)
                                        else:
                                            product = simple_product
                                        if product:
                                            product = \
                                                product[0].product_variant_ids[
                                                    0]

                                if products_data.get('type') == 'variable':
                                    # Create product variants for variable products
                                    self.variant_product_tmpl_create(
                                        products_data, instance_id)
                                    product = request.env[
                                        'product.product'].filtered(
                                        lambda r: r.woo_var_id == str(
                                            line_item['id']))
                                if product:
                                    val = {
                                        'name': product.name,
                                        'product_id': product.id,
                                        'product_uom_qty': line_item['quantity'],
                                        'price_unit': line_item['price'],
                                        'tax_id': tax_id.ids,
                                        'customer_lead': 1
                                    }
                                    orderline.append((0, 0, val))

                    # Process shipping lines from the response
                    for line_item in response.get('shipping_lines'):
                        if not line_item.get('method_id') or line_item.get(
                                'method_id') == 'other':
                            product = request.env.ref(
                                'woo_commerce.product_product_woocommerce_other').with_user(
                                SUPERUSER_ID)
                        elif line_item.get('method_id') == 'flat_rate':
                            product = request.env.ref(
                                'woo_commerce.product_product_flat_delivery').with_user(
                                SUPERUSER_ID)
                        elif line_item.get('method_id') == 'local_pickup':
                            product = request.env.ref(
                                'woo_commerce.product_product_local_pickup').with_user(
                                SUPERUSER_ID)
                        elif line_item.get('method_id') == 'pickup_location':
                            product = request.env.ref(
                                'woo_commerce.product_product_local_pickup').with_user(
                                SUPERUSER_ID)
                        elif line_item.get('method_id') == 'local_rate':
                            product = request.env.ref(
                                'woo_commerce.product_product_local_delivery').with_user(
                                SUPERUSER_ID)
                        elif line_item.get('method_id') == 'free_shipping':
                            product = request.env.ref(
                                'woo_commerce.product_product_woocommerce_free_delivery').with_user(
                                SUPERUSER_ID)
                        else:
                            product = False
                        val = {
                            'name': product.name,
                            'product_id': product.product_variant_ids[0].id,
                            'tax_id': False,
                            'price_unit': float(line_item['total']),
                            'product_uom_qty': 1,
                            'customer_lead': 1,
                        }
                        orderline.append((0, 0, val))

                    # Process fee lines from the response
                    if response.get('fee_lines'):
                        for line_item in response.get('fee_lines'):
                            product = request.env.ref(
                                'woo_commerce.woocommerce_fee_lines').with_user(
                                SUPERUSER_ID)
                            val = {
                                'name': product.name,
                                'product_id': product.product_variant_ids[0].id,
                                'tax_id': False,
                                'price_unit': float(line_item['total']),
                                'product_uom_qty': 1,
                                'customer_lead': 1,
                            }
                            orderline.append((0, 0, val))

                    # Process coupon lines from the response
                    if response.get('coupon_lines'):
                        for line_item in response.get('coupon_lines'):
                            if line_item.get('discount', None):
                                product = request.env.ref(
                                    'woo_commerce.woocommerce_coupons').with_user(
                                    SUPERUSER_ID)
                                val = {
                                    'name': product.name,
                                    'product_id': product.product_variant_ids[
                                        0].id,
                                    'tax_id': False,
                                    'price_unit': -1 * float(
                                        line_item['discount']),
                                    'product_uom_qty': 1,
                                    'customer_lead': 1,
                                }
                                orderline.append((0, 0, val))
                    # If there are order lines, update the value list
                    if orderline:
                        val_list['order_line'] = orderline
                    sale_order = request.env['sale.order'].with_user(
                        SUPERUSER_ID).create(val_list)
                    _logger.info(
                        "Sale order with ID %s has been successfully created.",
                        sale_order.id)
                    request.env['woo.logs'].with_user(SUPERUSER_ID).create({
                        'status': 'success',
                        'description': 'Orders %s with woo_id %s created '
                                       'successfully.' % (
                                           sale_order.name,
                                           str(response.get('id'))),
                        'trigger': 'import'
                    })
            except Exception as e:
                # Log exception error if there's a failure in the import process
                request.env['woo.logs'].sudo().create({
                    'status': 'failed',
                    'description': f"Failed to Create Webhook Order. Error: {str(e)}",
                    'trigger': 'import'
                })

    @http.route('/order/update', type='http', auth="none", csrf=False)
    def update_order(self, **kw):
        """
        Handle the order update webhook.
        """
        if not kw:
            response = request.get_json_data()
            _logger.info("Update WEBHOOK call for order: %s",
                         response)
            try:
                shop_name = request.httprequest.headers.get(
                    "X-WC-Webhook-Source").rstrip('/')
                instance_id = request.env[
                    "woo.commerce.instance"].sudo().search(
                    [("store_url", "ilike", shop_name)], limit=1)
                # Initialize WooCommerce API connection
                app = self.get_api(instance_id)
                # Check if the order with the given ID already exists in Odoo
                woo_ids = request.env['sale.order'].sudo().search([]).mapped(
                    'woo_id')
                # Continue with order creation only if it's not already in Odoo
                if str(response.get('id')) in woo_ids:
                    sale_order = request.env['sale.order'].sudo().search([
                        ('woo_id', '=', str(response.get('id'))),
                        ('instance_id', '=', instance_id.id)
                    ], limit=1)
                    if sale_order:
                        exist_partner = request.env[
                            'res.partner'].sudo().search(
                            [('type', '=', 'contact'),
                             ('woo_id', '=', str(response.get('customer_id'))),
                             ('instance_id', '=', instance_id.id)])
                        partner = ''

                        # Check if the partner exists, otherwise create a new one
                        if exist_partner:
                            partner = exist_partner.id
                        else:
                            # Check if the order is associated with a no user
                            app = self.get_api(instance_id)
                            customer_data = app.get(
                                'customers/%s' % response.get('customer_id'),
                                params={
                                    'per_page': 100, 'page': 1}).json()

                            if customer_data:
                                # creating a new partner
                                partner = (self.get_partner_for_single_order
                                           (response, customer_data,
                                            instance_id))

                        # Extract order creation date from the response
                        order_create_date = response.get('date_created')
                        date_time_obj = datetime.strptime(order_create_date,
                                                          '%Y-%m-%dT%H:%M:%S')

                        # Initialize state values for the sale order
                        # To Remove the order lines and Update it again
                        sale_order.with_user(SUPERUSER_ID).write(
                            {'state': 'draft'})

                        # Map WooCommerce order status to Odoo sale order states
                        if response.get('status') == 'pending':
                            state = 'draft'
                            woo_state = 'pending_payment'
                        elif response.get('status') == 'processing':
                            state = 'draft'
                            woo_state = 'processing'
                        elif response.get('status') == 'on-hold':
                            state = 'sale'
                            woo_state = 'on_hold'
                        elif response.get('status') == 'completed':
                            state = 'sale'
                            woo_state = 'completed'
                        elif response.get('status') == 'cancelled':
                            state = 'cancel'
                            woo_state = 'cancelled'
                        elif response.get('status') == 'refunded':
                            state = 'sale'
                            woo_state = 'refunded'
                        elif response.get('status') == 'failed':
                            state = 'cancel'
                            woo_state = 'failed'
                        elif response.get('status') == 'draft':
                            state = 'draft'
                            woo_state = 'draft'
                        else:
                            state = False
                            woo_state = False
                        # Prepare the values for creating the sale order
                        val_list = {
                            'partner_id': partner,
                            'date_order': date_time_obj,
                            'woo_id': response.get('id'),
                            'instance_id': instance_id.id if instance_id else False,
                            'woo_order_key': response.get('order_key'),
                            'state': state,
                            'woo_order_status': woo_state,
                            'company_id': instance_id.company_id.id if instance_id else False,
                            'currency_id': instance_id.currency if instance_id else False
                        }
                        orderline = []  # List to store order lines
                        # Process line items from the response
                        for line_item in response.get('line_items'):
                            woo_tax = []
                            for tax in line_item['taxes']:
                                woo_tax.append(str(tax['id']))

                            # Search for tax IDs in Odoo based on WooCommerce tax IDs
                            tax_id = request.env['account.tax'].sudo().search(
                                []).filtered(lambda r: r.woo_id in woo_tax)

                            main_product = request.env[
                                'product.template'].sudo().search([]).filtered(
                                lambda r: r.woo_id == str(
                                    line_item['product_id']))
                            if main_product:
                                main_product = main_product[0]
                                # Check if there are multiple variants for the main product
                                if len(main_product.product_variant_ids) > 1:
                                    product = request.env[
                                        'product.product'].sudo().search(
                                        []).filtered(
                                        lambda r: r.woo_var_id == str(
                                            line_item['variation_id']))
                                    if product:
                                        product = product[0]
                                else:
                                    # Use the main product if there is only one variant
                                    product = main_product.product_variant_ids[
                                        0]
                                if product:
                                    if response.get('status') == 'refunded':
                                        # For refunded products, set the price to 0
                                        val = {
                                            'name': product.name,
                                            'product_id': product.id,
                                            'price_unit': 0.0, # Set price to 0 for refunded products
                                            'product_uom_qty': line_item['quantity'],
                                            'tax_id': tax_id.ids,
                                            'customer_lead': 1,
                                        }
                                        orderline.append((0, 0, val))
                                    elif response.get('coupon_lines'):
                                        # For products with coupon lines, set the price without discounts
                                        val = {
                                            'name': product.name,
                                            'product_id': product.id,
                                            'product_uom_qty': line_item['quantity'],
                                            'tax_id': tax_id.ids,
                                            'customer_lead': 1,
                                        }
                                        orderline.append((0, 0, val))
                                    else:
                                        # For other products, set the price from the line item
                                        val = {
                                            'name': product.name,
                                            'product_id': product.id,
                                            'price_unit': line_item['price'],
                                            'product_uom_qty': line_item[
                                                'quantity'],
                                            'tax_id': tax_id.ids,
                                            'customer_lead': 1,
                                        }
                                        orderline.append((0, 0, val))
                            else:
                                # Create a new product if the main product doesn't exist
                                products_data = app.get(
                                    'products/%s' % line_item['product_id'],
                                    params={
                                        'per_page': 100, 'page': 1}).json()
                                if products_data.get('type') in ['simple',
                                                                 'variable',
                                                                 'bundle',
                                                                 'grouped',
                                                                 'external']:
                                    # Currently including these woocommerce
                                    # product types only
                                    product = False
                                    if products_data.get('type') in ['simple',
                                                                     'bundle']:
                                        # No need to create variants for these
                                        # products, so we can use a separate
                                        # function
                                        # Create a simple product without variants
                                        simple_product = self.simple_product_create(
                                            products_data, instance_id)
                                        if simple_product:
                                            if type(simple_product) == int:
                                                product = request.env[
                                                    'product.template'].sudo().browse(
                                                    simple_product)
                                            else:
                                                product = simple_product
                                            if product:
                                                product = \
                                                product[0].product_variant_ids[
                                                    0]

                                    if products_data.get('type') == 'variable':
                                        # Create product variants for variable products
                                        self.variant_product_tmpl_create(
                                            products_data, instance_id)
                                        product = request.env[
                                            'product.product'].filtered(
                                            lambda r: r.woo_var_id == str(
                                                line_item['id']))
                                    if product:
                                        val = {
                                            'name': product.name,
                                            'product_id': product.id,
                                            'product_uom_qty': line_item[
                                                'quantity'],
                                            'price_unit': line_item['price'],
                                            'tax_id': tax_id.ids,
                                            'customer_lead': 1
                                        }
                                        orderline.append((0, 0, val))

                            # Process shipping lines from the response
                            shipping_lines = []
                            for line_item in response.get('shipping_lines'):
                                if not line_item.get('method_id') or line_item.get('method_id') == 'other':
                                    product = request.env.ref(
                                        'woo_commerce.product_product_woocommerce_other').with_user(
                                        SUPERUSER_ID)
                                elif line_item.get('method_id') == 'flat_rate':
                                    product = request.env.ref(
                                        'woo_commerce.product_product_flat_delivery').with_user(
                                        SUPERUSER_ID)
                                elif line_item.get('method_id') == 'local_rate':
                                    product = request.env.ref(
                                        'woo_commerce.product_product_local_delivery').with_user(
                                        SUPERUSER_ID)
                                elif line_item.get('method_id') == 'local_pickup':
                                    product = request.env.ref(
                                        'woo_commerce.product_product_local_pickup').with_user(
                                        SUPERUSER_ID)
                                elif line_item.get('method_id') == 'pickup_location':
                                    product = request.env.ref(
                                        'woo_commerce.product_product_local_pickup').with_user(
                                        SUPERUSER_ID)
                                elif line_item.get('method_id') == 'free_shipping':
                                    product = request.env.ref(
                                        'woo_commerce.product_product_woocommerce_free_delivery').with_user(
                                        SUPERUSER_ID)
                                else:
                                    product = False
                                val = {
                                    'name': product.name,
                                    'product_id': product.product_variant_ids[
                                        0].id,
                                    'tax_id': False,
                                    'price_unit': float(line_item['total']),
                                    'product_uom_qty': 1,
                                    'customer_lead': 1,
                                }
                                shipping_lines.append((0, 0, val))
                            fee_lines = []
                            coupon_lines = []
                            # Process fee lines from the response
                            if response.get('fee_lines'):
                                for line_item in response.get('fee_lines'):
                                    product = request.env.ref(
                                        'woo_commerce.woocommerce_fee_lines').with_user(
                                        SUPERUSER_ID)
                                    val = {
                                        'name': product.name,
                                        'product_id':
                                            product.product_variant_ids[0].id,
                                        'tax_id': False,
                                        'price_unit': float(line_item['total']),
                                        'product_uom_qty': 1,
                                        'customer_lead': 1,
                                    }
                                    fee_lines.append((0, 0, val))
                            # Process coupon lines from the response
                            if response.get('coupon_lines'):
                                for line_item in response.get('coupon_lines'):
                                    if line_item.get('discount', None):
                                        product = request.env.ref(
                                            'woo_commerce.woocommerce_coupons').with_user(
                                            SUPERUSER_ID)
                                        val = {
                                            'name': product.name,
                                            'product_id':
                                                product.product_variant_ids[0].id,
                                            'tax_id': False,
                                            'price_unit': -1 * float(
                                                line_item['discount']),
                                            'product_uom_qty': 1,
                                            'customer_lead': 1,
                                        }
                                        coupon_lines.append((0, 0, val))
                        sale_order.order_line = False
                        sale_order.with_user(SUPERUSER_ID).write(val_list)
                        all_order_lines = orderline + fee_lines + coupon_lines + shipping_lines
                        if all_order_lines:
                            sale_order.with_user(SUPERUSER_ID).write(
                                {'order_line': all_order_lines})
                    _logger.info(
                        "Sale order with ID %s has been successfully updated.",
                        sale_order.id)
                    request.env['woo.logs'].with_user(SUPERUSER_ID).create({
                        'status': 'success',
                        'description': 'Orders %s with woo_id %s updated '
                                       'successfully.' % (
                                           sale_order.name,
                                           str(response.get('id'))),
                        'trigger': 'import'
                    })
            except Exception as e:
                # Log exception error if there's a failure in the import process
                request.env['woo.logs'].sudo().create({
                    'status': 'failed',
                    'description': f"Failed to import Woocommerce orders. Error: {str(e)}",
                    'trigger': 'import'
                })
