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


class SaleOrder(models.Model):
    """
    Class fpr the inherited model sale_order.Contains fields and methods
    related to Woocommerce sale order.
    Methods:
        compute_state_change(self):Method to compute invoiced quantity
            based on the Woocommerce status.
        get_tile_details(self):Method to return the count of instance,
            products, partners and orders to the dashboard.
        get_orders(self):Method to return order details to the dashboard.
        write(self, vals):Supering the write method to update order status
            of the Woocommerce according to the order status in Odoo.
        unlink(self):Supering the unlink function to delete sale order.
        sync_orders(self):Method to sync sale orders into Woocommerce.
    """
    _inherit = 'sale.order'

    woo_id = fields.Char(string='WooCommerce ID', copy=False,
                         help='Id in WooCommerce')
    woo_order_key = fields.Char(string='Order Key', readonly=True, copy=False,
                                help='Woo Commerce Order key')
    instance_id = fields.Many2one('woo.commerce.instance', string='Instance',
                                  readonly=True, copy=False,
                                  help='WooCommerce Instance id.')
    woo_order_status = fields.Selection(
        [('pending_payment', 'Pending Payment'), ('processing', 'Processing'),
         ('on_hold', 'On Hold'), ('completed', 'Completed'),
         ('cancelled', 'Cancelled'), ('refunded', 'Refunded'),
         ('failed', 'Failed'), ('draft', 'Draft')], default='draft',
        string='Woo Commerce Status', help='State of order in Woo commerce.')
    state_check = fields.Boolean(compute='compute_state_change',
                                 help='Field to check the state of the order')

    def compute_state_change(self):
        """
        Compute state_check based on WooCommerce status.

        TODO: FIX / Le code Cybrosys original forçait qty_invoiced = 0 sur les
        lignes de commande quand woo_order_status != 'completed', afin de
        bloquer invoice_status. Ce hack corrompait qty_invoiced (champ
        computed stored natif Odoo) et cassait :
          - la facturation partielle / split-facture
          - les acomptes (downpayment)
          - toute recompute native (Odoo écrase le hack)
        Solution à implémenter : bloquer la facturation via un override de
        _create_invoices() ou _get_invoiced() au lieu de manipuler
        qty_invoiced. Voir discussion party-mode 2026-03-16.
        """
        for order in self:
            order.state_check = bool(order.woo_order_status)

    @api.model
    def get_tile_details(self):
        """
        Method to return the count of instance, products, partners
        and orders to the dashboard.
            :return: Returns dictionary with the count of instance, products,
                partners and orders.
        """
        return {
            'instance': self.env['woo.commerce.instance'].search_count([]),
            'products': self.env['product.template'].search_count(
                [('woo_id', '!=', False)]),
            'partners': self.env['res.partner'].search_count(
                [('instance_id', '!=', False)]),
            'orders': self.env['sale.order'].search_count(
                [('woo_id', '!=', False)]),
        }

    @api.model
    def get_orders(self):
        """Method to return order details to the dashboard.
            :return: Returns list of dictionary with order details."""
        orders = self.env['sale.order'].search([('woo_id', '!=', False)])
        orders_list = []
        for order in orders:
            if order.invoice_status == 'no':
                status = 'Nothing to Invoice'
            elif order.invoice_status == 'to invoice':
                status = 'To Invoice'
            elif order.invoice_status == 'invoiced':
                status = 'Fully Invoiced'
            else:
                status = 'Upselling Opportunity'
            orders_list.append({
                'name': order.name,
                'date_order': order.date_order,
                'customer': order.partner_id.name,
                'total': order.amount_total,
                'status': status, })
        return orders_list

    def write(self, vals):
        """
        Supering the write method to update order status of the Woocommerce
        according to the order status in Odoo.
            :param vals: Dictionary with order data.
            :return: Returns record set of sale_order
        """
        result = super(SaleOrder, self).write(vals)
        if self.instance_id and self.instance_id.stage_change_orders:
            app = API(
                url="" + self.instance_id.store_url + "/index.php/", # Your store URL
                consumer_key=self.instance_id.consumer_key, # Your consumer key
                consumer_secret=self.instance_id.consumer_secret, # Your consumer secret
                wp_api=True,  # Enable the WP REST API integration
                version="wc/v3",  # WooCommerce WP REST API version
                timeout=500,
            )
            if self.woo_order_status == 'pending_payment':
                status = 'pending'
            elif self.woo_order_status == 'processing':
                status = 'processing'
            elif self.woo_order_status == 'on_hold':
                status = 'on-hold'
            elif self.woo_order_status == 'completed':
                status = 'completed'
            elif self.woo_order_status == 'refunded':
                status = 'refunded'
            elif self.woo_order_status == 'failed':
                status = 'failed'
            elif self.woo_order_status == 'draft':
                status = 'draft'
            elif self.woo_order_status == 'cancelled':
                status = 'cancelled'
            else:
                status = False
            val_list = {
                'status': status
            }
            app.put(f"orders/{self.woo_id}", val_list).json()
        return result

    def action_delete_from_woo(self):
        """
        Delete the order from WooCommerce and remove it from Odoo.
        """
        for order in self:
            if not order.instance_id or not order.woo_id:
                continue
            wcapi = API(
                url="" + order.instance_id.store_url + "/index.php/",
                consumer_key=order.instance_id.consumer_key,
                consumer_secret=order.instance_id.consumer_secret,
                wp_api=True,
                version="wc/v3"
            )
            wcapi.delete(f"orders/{order.woo_id}", params={"force": True}).json()
            order.unlink()

    def action_cancel(self):
        """
        Cancel the order in WooCommerce and then call Odoo's default
        cancel action.
        """
        if self.instance_id and self.woo_id:
            self.action_cancel_from_woo()
        return super(SaleOrder, self).action_cancel()

    def action_cancel_from_woo(self):
        """
        Update the order status to 'cancelled' in WooCommerce.
        """
        for order in self:
            if not order.instance_id or not order.woo_id:
                continue
            data = {
                "status": "cancelled"
            }
            wcapi = API(
                url="" + order.instance_id.store_url + "/index.php/",
                consumer_key=order.instance_id.consumer_key,
                consumer_secret=order.instance_id.consumer_secret,
                wp_api=True,
                version="wc/v3"
            )
            wcapi.put(f"orders/{order.woo_id}", data)

    def unlink(self):
        """
        Supering the unlink function to delete sale order.
            :return: Returns record set of sale order.
        """
        for order in self:
            if order.instance_id and order.instance_id.delete_orders:
                app = API(
                    url="" + self.instance_id.store_url + "/index.php/", # Your store URL
                    consumer_key=self.instance_id.consumer_key, # Your consumer key
                    consumer_secret=self.instance_id.consumer_secret, # Your consumer secret
                    wp_api=True,  # Enable the WP REST API integration
                    version="wc/v3",  # WooCommerce WP REST API version
                    timeout=500,
                )
                app.delete(f"orders/{order.woo_id}",
                           params={"force": True}).json()
            return super(SaleOrder, self).unlink()

    def sync_orders(self):
        """
        Method to sync sale orders into Woocommerce.
            :return: Returns window action of model woo update.
        """
        return {
            'name': _('Sync Orders'),
            'view_mode': 'form',
            'res_model': 'woo.update',
            'view_id': self.env.ref('woo_commerce.woo_update_view_form').id,
            'type': 'ir.actions.act_window',
            'context': {
                'operation_type': 'orders',
                'active_ids': self.ids,
            },
            'target': 'new'
        }
