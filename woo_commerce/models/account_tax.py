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
from odoo import fields, models


class AccountTax(models.Model):
    """
    Class of inherited model account_tax. Contains fields for Woocommerce
    id and instance id of tax and tax class.
    """
    _inherit = 'account.tax'

    woo_id = fields.Char(string='WooCommerce ID', readonly=True, copy=False,
                         help='Id in WooCommerce')
    instance_id = fields.Many2one('woo.commerce.instance', string='Instance',
                                  readonly=True, copy=False,
                                  help='WooCommerce Instance id')
    tax_class = fields.Char(string='Tax Class', readonly=True, copy=False,
                            help='Class of the tax')


class AccountTaxGroup(models.Model):
    """
    Class of inherited model account_tax_group. Contains fields for
    Woocommerce id and instance id of tax group.
    """
    _inherit = 'account.tax.group'
    _description = 'Account Tax Group'

    woo_id = fields.Char(string='WooCommerce ID', readonly=True, copy=False,
                         help='Id in WooCommerce')
    instance_id = fields.Many2one('woo.commerce.instance', string='Instance',
                                  readonly=True, copy=False,
                                  help='WooCommerce Instance id')
