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
import re
import requests
from woocommerce import API
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class WooCommerceInstance(models.Model):
    """
    Class for the model woo_commerce_instance.Contains fields and methods
    of the Woocommerce instance.
    """
    _name = 'woo.commerce.instance'
    _description = 'WooCommerce Instance'

    name = fields.Char(string='Instance Name', required=True,
                       help='Name of the Instance')
    color = fields.Integer(string='Color', help='Color for the Kanban')
    consumer_key = fields.Char(string='Consumer Key', required=True,
                               help='Consumer key of the woocommerce')
    consumer_secret = fields.Char(string='Consumer Secret', required=True,
                                  help='Consumer Secret of the woo commerce.')
    store_url = fields.Char(string='Store URL', required=True,
                            help='Woo commerce store Url')
    currency = fields.Char('Currency', readonly=True, help='Related Currency')
    company_id = fields.Many2one('res.company', help='Company of the Instance',
                                 default=lambda self: self.env.company)
    api_key = fields.Char(string='Api Key', required=True,
                          help='API Key for the instance.')
    state = fields.Selection([('not_connected', 'Not Connected'),
                              ('connected', 'Connected')],
                             default='not_connected',
                             help='State of the instance')
    delete_orders = fields.Boolean(string='Delete Orders',
                                   help='Enabling this option will '
                                        'synchronize the deletion of orders '
                                        'between Odoo and WooCommerce. When a '
                                        'corresponding order is deleted in '
                                        'Odoo, the WooCommerce order will '
                                        'also be deleted.')
    stage_change_orders = fields.Boolean(string='State Orders',
                                         help='Enabling this option will '
                                              'synchronize the state of orders '
                                              'between Odoo and WooCommerce. '
                                              'When a corresponding order  '
                                              'WooCommerce status is changed it'
                                              'will change status of the '
                                              'current order')
    product_delete = fields.Boolean(string='Product Delete',
                                    help='Enabling this option will '
                                         'synchronize the deletion of Products '
                                         'between Odoo and WooCommerce. When a '
                                         'corresponding product is deleted in '
                                         'Odoo, the WooCommerce product will '
                                         'also be deleted.')
    customer_delete = fields.Boolean(string='Customer Delete',
                                     help='Enabling this option will '
                                          'synchronize the deletion of Customer'
                                          'between Odoo and WooCommerce. When a'
                                          'corresponding Customer is deleted in'
                                          'Odoo, the WooCommerce Customer will '
                                          'also be deleted.')
    pending_count_logs = fields.Integer(string='Pending logs',
                                        compute='_compute_logs_count',
                                        help='The Pending logs count')
    completed_count_logs = fields.Integer(string='Completed Logs',
                                          compute='_compute_logs_count',
                                          help='Complete logs count')
    failed_count_logs = fields.Integer(string='Failed Logs ',
                                       compute='_compute_logs_count',
                                       help='Failed logs count')

    def _compute_logs_count(self):
        """
        Compute the count of pending, completed, and failed Woo logs for
        each instance in a more efficient way by reducing the number of
        queries.
        """
        job_cron_model = self.env['job.cron']
        for instance in self:
            logs = job_cron_model.read_group(
                [('instance_id', '=', instance.id)],
                ['state'],
                ['state']
            )
            counts = {log['state']: log['state_count'] for log in logs}
            instance.pending_count_logs = counts.get('pending', 0)
            instance.completed_count_logs = counts.get('done', 0)
            instance.failed_count_logs = counts.get('fail', 0)

    @api.onchange('customer_delete', 'product_delete', 'delete_orders',
                  'stage_change_orders')
    def _onchange_warning_fields(self):
        """
        On change method triggered when certain fields are modified.
        Displays a warning about the synchronization between Odoo and
        WooCommerce for customer, product, order deletion, and order stage
        changes.
        """
        if self.customer_delete:
            return {
                'warning': {
                    'title': _('Warning!'),
                    'message': _(
                        'Enabling "Delete Customer" will synchronize customer '
                        'deletion between Odoo and WooCommerce. Proceed with '
                        'caution.'),
                }
            }
        elif self.product_delete:
            return {
                'warning': {
                    'title': _('Warning!'),
                    'message': _(
                        'Enabling "Delete Product" will synchronize product '
                        'deletion between Odoo and WooCommerce. Proceed with '
                        'caution.'),
                }
            }
        elif self.delete_orders:
            return {
                'warning': {
                    'title': _('Warning!'),
                    'message': _(
                        'Enabling "Delete Orders" will synchronize order '
                        'deletion between Odoo and WooCommerce. Proceed with '
                        'caution.'),
                }
            }
        elif self.stage_change_orders:
            return {
                'warning': {
                    'title': _('Warning!'),
                    'message': _(
                        'Enabling "Stage Orders" will synchronize the order '
                        'stage between Odoo and WooCommerce. Any changes in '
                        'WooCommerce order stage will be reflected in Odoo. '
                        'Proceed with caution.'),
                }
            }

    @api.model
    def get_instance_graph(self):
        """
        Method to return product, customer, order and instance details
        to the dashboard.
            :return: Returns dictionary with dashboard details.
        """
        instance_records = self.env['woo.commerce.instance'].search([])
        product_count = [self.env['product.template'].search_count(
            [('instance_id', '=', rec.id)]) for rec in instance_records]
        customer_count = [self.env['res.partner'].search_count(
            [('instance_id', '=', rec.id)]) for rec in instance_records]
        order_count = [self.env['sale.order'].search_count(
            [('instance_id', '=', rec.id)]) for rec in instance_records]
        instance_name = [rec.name for rec in instance_records]
        return {
            'instance_name': instance_name,
            'product_len': product_count,
            'customer_len': customer_count,
            'order_len': order_count
        }

    def get_wizard(self):
        """
        Function used for returning wizard view for operations.
        :return: Returns window action of woo_operation model.
        """
        set_woo_api = API(
            url=self.store_url + "/index.php/wp-json/wc/v3/system_status?",
            consumer_key=self.consumer_key,  # Your consumer key
            consumer_secret=self.consumer_secret,  # Your consumer secret
            wp_api=True,  # Enable the WP REST API integration
            version="wc/v3",  # WooCommerce WP REST API version
            timeout=500
        )
        set_res = set_woo_api.get("").json()
        self.currency = set_res['settings'].get('currency')
        return {
            'name': _('Instance Operations'),
            'view_mode': 'form',
            'res_model': 'woo.operation',
            'domain': [],
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': {
                'default_name': self.name,
                'default_consumer_key': self.consumer_key,
                'default_consumer_secret': self.consumer_secret,
                'default_store_url': self.store_url,
                'default_api_key': self.api_key,
                'default_currency': self.currency,
                'default_company': self.company_id
            }
        }

    def get_instance(self):
        """
        Method for returning current form view of instance.
        :return: Returns window action of woo_commerce_instance model.
        """
        return {
            'name': _('Instance'),
            'view_mode': 'form',
            'res_model': 'woo.commerce.instance',
            'res_id': self.id,
            'domain': [],
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

    @api.model_create_multi
    def create(self, vals_list):
        """
        Supering the create function to checks all the connection validations.
        :param vals_list: Dictionary of record values.
        :return: Returns record set of WooCommerceInstance.
        """
        attachment_id = self.env['ir.attachment'].sudo().search(
            [('res_model', '=', 'product.template'),
             ('res_field', '=', 'image_1920')])
        if attachment_id:
            attachment_id.public = True
        for item in vals_list:
            site_url = item['store_url']
            set_woo_api = API(
                url=f"{site_url}/index.php/wp-json/wc/v3/system_status?",
                consumer_key=item['consumer_key'],
                consumer_secret=item['consumer_secret'],
                wp_api=True,  # Enable the WP REST API integration
                version="wc/v3",  # WooCommerce WP REST API version
                timeout=500,
            )
            regex = re.compile(
                r'^(?:http|ftp)s?://'  # http:// or https://
                r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
                r'localhost|'  # localhost...
                r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
                r'(?::\d+)?'  # optional port
                r'(?:/?|[/?]\S+)$', re.IGNORECASE)
            url_status = re.match(regex, set_woo_api.url) is not None
            if not url_status:
                raise UserError(_("URL Doesn't Exist."))
            try:
                requests.get(set_woo_api.url)
            except requests.ConnectionError as exception:
                raise UserError(_("URL Doesn't Exist."))
            if set_woo_api.get("").status_code != 200:
                raise UserError(_("URL Doesn't Exist or Authentication Issue."))
            set_res = set_woo_api.get("").json()
            if set_res['settings']:
                item['currency'] = set_res['settings'].get('currency')
                if item['currency']:
                    item['state'] = 'connected'
            # Validate the API key
            api_key = item.get('api_key', '')
            if api_key and (
                len(api_key) != 40 or not re.match(r'^[A-Za-z0-9]+$', api_key)):
                raise ValidationError(_("Invalid API Key Credentials"))
        return super(WooCommerceInstance, self).create(vals_list)

    def write(self, vals):
        """
         Supering the write function to prevent the credentials changing.
        :param vals: Dictionary of record values.
        :return: Returns the record set of WooCommerceInstance.
        """
        attachment_id = self.env['ir.attachment'].sudo().search(
            [('res_model', '=', 'product.template'),
             ('res_field', '=', 'image_1920')])
        if attachment_id:
            attachment_id.public = True
        keys = ['store_url', 'consumer_key', 'consumer_secret']
        for key in keys:
            if key in vals.keys():
                raise UserError(_("You Can't Change Credential Details Ones "
                                  "it was created."))
        # Validate the API key
        if 'api_key' in vals:
            api_key = vals.get('api_key', '')
            if len(api_key) != 40 or not re.match(r'^[A-Za-z0-9]+$', api_key):
                raise ValidationError(_("Invalid API Key Credentials"))
        return super(WooCommerceInstance, self).write(vals)

    def get_completed_instance_woo_logs(self):
        """
        Get action to display completed Woo logs associated with the instance.
        """
        return {
            'type': 'ir.actions.act_window',
            'name': _('Completed Woo Logs'),
            'domain': [('instance_id', '=', self.id), ('state', '=', 'done')],
            'view_mode': 'list,form',
            'res_model': 'job.cron',
            'context': {'create': False, 'edit': False},
        }

    def get_pending_instance_woo_logs(self):
        """
        Get action to display pending Woo logs associated with the instance.
        """
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pending Woo Logs'),
            'domain': [('instance_id', '=', self.id),
                       ('state', '=', 'pending')],
            'view_mode': 'list,form',
            'res_model': 'job.cron',
            'context': {'create': False, 'edit': False},
        }

    def get_failed_instance_woo_logs(self):
        """
        Get action to display failed Woo logs associated with the instance.
        """
        return {
            'type': 'ir.actions.act_window',
            'name': _('Failed Woo Logs'),
            'domain': [('instance_id', '=', self.id), ('state', '=', 'fail')],
            'view_mode': 'list,form',
            'res_model': 'job.cron',
            'context': {'create': False, 'edit': False},
        }

    def sync_cron(self):
        """
        Method of scheduled action that call another function to syncs
        Woocommerce data.
        """
        woo_operation = self.env['woo.operation'].search([])
        if woo_operation:
            woo_operation[0].sync_details()
