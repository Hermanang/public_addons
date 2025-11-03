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


class ResPartner(models.Model):
    """
    Class for the inherited model res_partner. Contains fields and methods
    related to Woocommerce partner.
    """
    _inherit = 'res.partner'
    _description = 'Res Partner'

    woo_id = fields.Char(string='WooCommerce ID', readonly=True, copy=False,
                         help='Id in WooCommerce')
    woo_user_name = fields.Char(string='User Name', readonly=True, copy=False,
                                help='User name in Woo commerce.')
    instance_id = fields.Many2one('woo.commerce.instance', string='Instance',
                                  readonly=True, copy=False,
                                  help='WooCommerce Instance id.')

    @api.constrains('email')
    def _check_unique_email(self):
        """
        Method to check if there is any duplicates in the email.
        """
        for record in self:
            if record.email:
                duplicate_records = self.search(
                    [('type', '=', 'contact'), ('id', '!=', record.id),
                     ('email', '=', record.email.lower())], limit=1)
                if duplicate_records:
                    self.env['woo.logs'].sudo().create([{
                        'status': 'failed',
                        'description': f"The email '{record.email}'"
                                       f" already exists for record with ID"
                                       f" {record.name}",
                        'trigger': 'import'
                    }])
                    continue

    def image_upload(self, partner):
        """
         Method to Upload partner image into WordPress media to get a public
         link.
        """
        attachment_id = self.env['ir.attachment'].sudo().search(
            [('res_model', '=', 'res.partner'),
             ('res_id', '=', partner.id),
             ('res_field', '=', 'image_1920')])
        product_image_url = False
        if attachment_id:
            attachment_id.write({'public': True})
            base_url = self.env['ir.config_parameter'].sudo().get_param(
                'web.base.url')
            product_image_url = f"{base_url}{attachment_id.image_src}.jpg"
        return product_image_url

    def sync_customers(self):
        """
        Method to sync customers into Woocommerce.
            :return: Returns window action of model woo_update.
        """
        return {
            'name': _('Sync Customers'),
            'view_mode': 'form',
            'res_model': 'woo.update',
            'view_id': self.env.ref('woo_commerce.woo_update_view_form').id,
            'type': 'ir.actions.act_window',
            'context': {
                'operation_type': 'customers',
                'active_ids': self.ids
            },
            'target': 'new'
        }

    def unlink(self):
        """
        Supering unlink function for deleting values on all instances.
            :return: Record set of ResPartner.
        """
        for partner_id in self:
            if partner_id.instance_id and partner_id.type == 'contact'and partner_id.instance_id.customer_delete:
                app = API(
                    url="" + partner_id.instance_id.store_url + "/index.php/", # Your store URL
                    consumer_key=partner_id.instance_id.consumer_key, # Your consumer key
                    consumer_secret=partner_id.instance_id.consumer_secret, # Your consumer secret
                    wp_api=True,  # Enable the WP REST API integration
                    version="wc/v3",  # WooCommerce WP REST API version
                    timeout=500,
                )
                app.delete(f"customers/{partner_id.woo_id}",
                           params={"force": True}).json()
        return super(ResPartner, self).unlink()

    def woo_update(self, instance_id):
        """
        Method to update partner into Woocommerce.
            :param instance_id: id of the instance.
        """
        for partner_id in self:
            if instance_id and partner_id.email and partner_id.type == 'contact':
                name = partner_id.name.rsplit(' ', 1)
                val_list = {
                    "first_name": name[0],
                    "last_name": name[1] if len(name) > 1 else "",
                    'email': partner_id.email if partner_id.email else "",
                    'role': 'customer',
                    'billing': {
                        "first_name": name[0],
                        "last_name": name[1] if len(name) > 1 else "",
                        "company": "",
                        "address_1": partner_id.street if partner_id.street else "",
                        "address_2": "",
                        "city": partner_id.city if partner_id.city else "",
                        "state": partner_id.state_id.code if partner_id.state_id else "",
                        "postcode": partner_id.zip if partner_id.zip else "",
                        "country": partner_id.country_id.code if partner_id.country_id else "",
                        "email": partner_id.email if partner_id.email else
                        partner_id.name.split()[0] + "@gmail.com",
                        "phone": partner_id.phone if partner_id.phone else ""
                    },
                    'shipping': {
                        "first_name": name[0],
                        "last_name": name[1] if len(name) > 1 else "",
                        "company": "",
                        "address_1": partner_id.street if partner_id.street else "",
                        "address_2": "",
                        "city": partner_id.city if partner_id.city else "",
                        "state": partner_id.state_id.code if partner_id.state_id else "",
                        "postcode": partner_id.zip if partner_id.zip else "",
                    },
                    "is_paying_customer": False,
                    "avatar_url": self.image_upload(partner_id),
                    "meta_data": [],
                }
                if partner_id.instance_id:
                    app = API(
                        url="" + instance_id.store_url + "/index.php/", # Your store URL
                        consumer_key=instance_id.consumer_key, # Your consumer key
                        consumer_secret=instance_id.consumer_secret, # Your consumer secret
                        wp_api=True, # Enable the WP REST API integration
                        version="wc/v3", # WooCommerce WP REST API version
                        timeout=500,
                    )
                    res = app.put(f"customers/{partner_id.woo_id}",
                                  val_list).json()
                    if res.get('id'):
                        partner_id.write({
                            'woo_id': res.get('id'),
                            'instance_id': instance_id.id,
                            'woo_user_name': res.get('username')
                        })
                else:
                    app = API(
                        url="" + instance_id.store_url + "/index.php/", # Your store URL
                        consumer_key=instance_id.consumer_key, # Your consumer key
                        consumer_secret=instance_id.consumer_secret, # Your consumer secret
                        wp_api=True, # Enable the WP REST API integration
                        version="wc/v3", # WooCommerce WP REST API version
                        timeout=500,
                    )
                    res = app.post('customers', val_list).json()
                    if res.get('id'):
                        partner_id.write({
                            'woo_id': res.get('id'),
                            'instance_id': instance_id.id,
                            'woo_user_name': res.get('username')
                        })
