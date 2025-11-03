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
from odoo.exceptions import UserError

category_ids = False
attribute_ids = False
api_res = False
auth_vals = False


class WooUpdate(models.TransientModel):
    """
        Model for Woocommerce Update Wizard.
        This wizard allows users to update/export product, customer, or order
        records from Odoo to WooCommerce for a selected instance.
    """
    _name = 'woo.update'
    _description = 'Woo Update'

    instance_id = fields.Many2one('woo.commerce.instance', string='Instance',
                                  copy=False, help='WooCommerce Instance id.')

    @api.model
    def default_get(self, fields):
        """
        Get default values for the wizard.
        This function sets the default instance value based on the connected
        WooCommerce instance.
        """
        defaults = super().default_get(fields)
        current_instance = self.env['woo.commerce.instance'].search(
            [('state', '=', 'connected')])
        if len(current_instance) == 1:
            defaults['instance_id'] = current_instance.id
        return defaults

    def update_records(self):
        """
        Update/Export records to WooCommerce.
        This function updates or exports product, customer, or order records from
        Odoo to WooCommerce based on the selected operation type.
        """
        if not self.instance_id:
            raise UserError(
                _("Instance field is mandatory for updating records."))
        records = self._context.get('active_ids')
        if self._context.get('operation_type') == 'products':
            objs = self.env['product.template'].browse(records)
            wizard = self.get_wizard(self.instance_id)
            wizard.update_to_woo_commerce(self.instance_id, objs, 'products')
        if self._context.get('operation_type') == 'customers':
            objs = self.env['res.partner'].browse(records).filtered(
                lambda x: x.type == 'contact')
            wizard = self.get_wizard(self.instance_id)
            wizard.update_to_woo_commerce(self.instance_id, objs, 'customers')
        if self._context.get('operation_type') == 'orders':
            objs = self.env['sale.order'].browse(records)
            wizard = self.get_wizard(self.instance_id)
            wizard.update_to_woo_commerce(self.instance_id, objs, 'orders')

    def get_wizard(self, instance_id):
        """
        Get a new Woo Operation wizard.
        This function returns a new wizard for performing WooCommerce
        operations.
        """
        set_wcapi = API(
            url=instance_id.store_url + "/index.php/wp-json/wc/v3/system_status?",
            consumer_key=instance_id.consumer_key,  # Your consumer key
            consumer_secret=instance_id.consumer_secret,  # Your consumer secret
            wp_api=True,  # Enable the WP REST API integration
            version="wc/v3",  # WooCommerce WP REST API version
            timeout=500
        )
        set_res = set_wcapi.get("").json()
        currency = set_res['settings'].get('currency')
        instance_id.currency = currency
        wizard = self.env['woo.operation'].with_context({
            'default_name': instance_id.name,
            'default_consumer_key': instance_id.consumer_key,
            'default_consumer_secret': instance_id.consumer_secret,
            'default_store_url': instance_id.store_url,
            'default_api_key': instance_id.api_key,
            'default_currency': instance_id.currency,
            'default_company': instance_id.company_id
        }).create({})
        return wizard
