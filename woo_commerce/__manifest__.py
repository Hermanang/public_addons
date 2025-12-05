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
{
    'name': 'Odoo WooCommerce Connector',
    'version': '18.0.1.0.6',
    'category': 'Ecommerce',
    'summary': 'Odoo WooCommerce Connector for seamless integration between '
               'Odoo and WooCommerce. Sync customers, products, and orders '
               'efficiently',
    'description': """Streamline your business operations by synchronizing 
                   customers, products, and orders in real-time between 
                   Odoo and WooCommerce. Our connector offers easy imports 
                   from WooCommerce to Odoo and smooth exports, optimizing 
                   data flow. Utilize queue jobs to enhance synchronization 
                   efficiency and ensure uninterrupted workflows. Stay 
                   responsive with instant notifications for a seamless 
                   integration experience""",
    'author': 'Cybrosys Techno Solutions',
    'maintainer': 'Cybrosys Techno Solutions',
    'company': 'Cybrosys Techno Solutions',
    'website': 'https://www.cybrosys.com',
    'depends': ['website_sale', 'stock', 'sale_management', 'account',
                'sale_stock'],
    'data': [
        'data/woo_commerce_data.xml',
        'data/ir_actions_data.xml',
        'data/ir_cron_data.xml',
        'security/ir.model.access.csv',
        'views/woo_commerce_instance_views.xml',
        'views/woo_attribute_mapping_views.xml',
        'views/job_cron_views.xml',
        'views/woo_logs_views.xml',
        'views/product_category_views.xml',
        'views/product_attribute_views.xml',
        'views/account_tax_views.xml',
        'views/product_views.xml',
        'views/sale_order_views.xml',
        'views/res_partner_views.xml',
        'wizard/woo_operation_views.xml',
        'wizard/woo_update_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'woo_commerce/static/src/js/dashboard.js',
            'woo_commerce/static/src/xml/dashboard.xml',
            'woo_commerce/static/src/css/dashboard.css',
            'woo_commerce/static/src/js/lib/Chart.bundle.js',
        ],
    },
    'images': ['static/description/banner.jpg'],
    "external_dependencies": {"python": ["WooCommerce"]},
    'license': 'OPL-1',
    'price': 79,
    'currency': 'EUR',
    'installable': True,
    'application': True,
    'auto_install': False,
}
