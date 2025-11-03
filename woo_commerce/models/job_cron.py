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
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class JobCron(models.Model):
    """
    Class for recording jobs to be done to sync woo commerce and odoo.
    Methods:
        _do_job(self):cron function to perform job created in specific
        interval.
    """
    _name = 'job.cron'
    _description = 'Cron Job'
    _rec_name = 'model_id'

    model_id = fields.Many2one('ir.model', string='Model',
                               help='Model where the function written')
    instance_id = fields.Many2one('woo.commerce.instance',
                                  help='Instance Id on which have to '
                                       'sync the record', string='Instance')
    function = fields.Char(string='Function', help='Function to be performed')
    data = fields.Json(string='Data', help='Data, arguments for the function')
    state = fields.Selection([('pending', 'Pending'), ('done', 'Done'),
                              ('failed', 'Failed')], help='Status of record',
                             string='State', default='pending', readonly=True)

    @api.model
    def _do_job(self):
        """
        Method to do cron jobs for exporting and importing data.
        """
        job = self.env['job.cron'].sudo().search([('state', '=', 'pending')],
                                                 order='id asc', limit=1)
        for rec in job:
            if rec:
                model = self.env[rec.model_id.model].sudo().search([])
                if rec.function == "product_create":
                    try:
                        model.product_create(rec.data, rec.instance_id)
                        rec.state = "done"
                    except Exception as e:
                        _logger.error('Some error has been occurred in the '
                                      'processing of function:product_create')
                        number_of_items = len(
                            list(filter(lambda x: isinstance(x, dict),
                                        rec.data)))
                        self.env['woo.logs'].sudo().create([{
                            'status': 'failed',
                            'trigger': 'import',
                            'description': f'An exception error occurred '
                                           f'during the processing of the '
                                           f'"product_create" function.'
                                           f'{number_of_items}'
                                           f' product item  failed to Import.'
                                           f' Error: {str(e)}',
                        }])
                        rec.state = "failed"
                if rec.function == "product_data_post":
                    try:
                        model.product_data_post(rec.data, rec.instance_id)
                        rec.state = "done"
                    except Exception as e:
                        _logger.error(
                            'Some error has been occurred in the processing'
                            ' of function:product_data_post')
                        self.env['woo.logs'].sudo().create([{
                            'status': 'failed',
                            'trigger': 'export',
                            'description': f'An exception error occurred '
                                           f'during the processing of the '
                                           f'"product_data_post" function.'
                                           f'Error: {str(e)}',
                        }])
                        rec.state = "failed"
                if rec.function == "customer_data_post":
                    try:
                        model.customer_data_post(rec.data, rec.instance_id)
                        rec.state = "done"
                    except Exception as e:
                        _logger.error(
                            'Some error has been occurred in the processing'
                            ' of function:customer_data_post')
                        self.env['woo.logs'].sudo().create([{
                            'status': 'failed',
                            'trigger': 'export',
                            'description': f'An exception error occurred '
                                           f'during the processing of the '
                                           f'"customer_data_post" function.'
                                           f'Error: {str(e)}',
                        }])
                        rec.state = "failed"
                if rec.function == "customer_data_woo_update":
                    try:
                        model.customer_data_woo_update(rec.data,
                                                       rec.instance_id)
                        rec.state = "done"
                    except Exception as e:
                        _logger.info('Some error has been occurred in the '
                                     'processing of '
                                     'function:customer_data_woo_update')
                        self.env['woo.logs'].sudo().create([{
                            'status': 'failed',
                            'trigger': 'export',
                            'description': f'An exception error occurred '
                                           f'during the processing of the '
                                           f'"customer_data_woo_update" function.'
                                           f'Error: {str(e)}',
                        }])
                        rec.state = "failed"
                if rec.function == "customer_create":
                    try:
                        model.customer_create(rec.data, rec.instance_id)
                        rec.state = "done"
                    except Exception as e:
                        _logger.info('Some error has been occurred in the '
                                     'processing of '
                                     'function:customer_create')
                        number_of_items = len(
                            list(filter(lambda x: isinstance(x, dict),
                                        rec.data)))
                        self.env['woo.logs'].sudo().create([{
                            'status': 'failed',
                            'trigger': 'import',
                            'description': f'An exception error occurred '
                                           f'during the processing of the '
                                           f'"customer_create" function.'
                                           f'{number_of_items}'
                                           f' Customer item  failed to Import.'
                                           f' Error: {str(e)}',
                        }])
                        rec.state = "failed"

                if rec.function == "export_selected_product_categories":
                    try:
                        model.export_selected_product_categories(rec.data,
                                                                rec.instance_id)
                        rec.state = "done"
                    except Exception as e:
                        _logger.error(
                            'Some error has occurred in the processing '
                            'of function: export_selected_product_categories'
                        )
                        self.env['woo.logs'].sudo().create({
                            'status': 'failed',
                            'trigger': 'export',
                            'description': f'An exception error occurred '
                                           f'during the processing of the '
                                           f'"export_selected_product_categories" function. '
                                           f'Error: {str(e)}',
                        })
                        rec.state = "failed"

                if rec.function == "export_selected_product_attributes":
                    try:
                        model.export_selected_product_attributes(rec.data,
                                                                rec.instance_id)
                        rec.state = "done"
                    except Exception as e:
                        _logger.error(
                            'Some error has occurred in the processing '
                            'of function: export_selected_product_attributes'
                        )
                        self.env['woo.logs'].sudo().create({
                            'status': 'failed',
                            'trigger': 'export',
                            'description': f'An exception error occurred '
                                           f'during the processing of the '
                                           f'"export_selected_product_attributes" function. '
                                           f'Error: {str(e)}',
                        })
                        rec.state = "failed"


                if rec.function == "export_selected_product_tags":
                    try:
                        model.export_selected_product_tags(rec.data,
                                                          rec.instance_id)
                        rec.state = "done"
                    except Exception as e:
                        _logger.error(
                            'Some error has occurred in the processing '
                            'of function: export_selected_product_tags'
                        )
                        self.env['woo.logs'].sudo().create({
                            'status': 'failed',
                            'trigger': 'export',
                            'description': f'An exception error occurred '
                                           f'during the processing of the '
                                           f'"export_selected_product_tags" function. '
                                           f'Error: {str(e)}',
                        })
                        rec.state = "failed"

                if rec.function == "product_data_woo_update":
                    try:
                        model.product_data_woo_update(rec.data,
                                                      rec.instance_id)
                        rec.state = "done"
                    except Exception as e:
                        _logger.info('Some error has been occurred in the '
                                     'processing of '
                                     'function:product_data_woo_update')
                        self.env['woo.logs'].sudo().create([{
                            'status': 'failed',
                            'trigger': 'export',
                            'description': f'An exception error occurred '
                                           f'during the processing of the '
                                           f'"product_data_woo_update" function.'
                                           f'Error: {str(e)}',
                        }])
                        rec.state = "failed"
                if rec.function == "order_data_woo_update":
                    try:
                        model.order_data_woo_update(rec.data, rec.instance_id)
                        rec.state = "done"
                    except Exception as e:
                        _logger.info('Some error has been occurred in the'
                                     ' processing of '
                                     'function:order_data_woo_update')
                        self.env['woo.logs'].sudo().create([{
                            'status': 'failed',
                            'trigger': 'export',
                            'description': f'An exception error occurred '
                                           f'during the processing of the '
                                           f'"order_data_woo_update" function.'
                                           f'Error: {str(e)}',
                        }])
                        rec.state = "failed"
                if rec.function == "category_data_post":
                    try:
                        model.category_data_post(rec.data, rec.instance_id)
                        rec.state = "done"
                    except Exception as e:
                        _logger.info('Some error has been occurred in the'
                                     ' processing of '
                                     'function:category_data_post')
                        self.env['woo.logs'].sudo().create({
                            'status': 'failed',
                            'trigger': 'export',
                            'description': f'An exception error occurred '
                                           f'during the processing of the '
                                           f'"category_data_post" function.'
                                           f'Error: {str(e)}',
                        })
                        rec.state = "failed"
                if rec.function == "attribute_data_post":
                    try:
                        model.attribute_data_post(rec.data, rec.instance_id)
                        rec.state = "done"
                    except Exception as e:
                        _logger.info('Some error has been occurred in the'
                                     ' processing of '
                                     'function:attribute_data_post')
                        self.env['woo.logs'].sudo().create({
                            'status': 'failed',
                            'trigger': 'export',
                            'description': f'An exception error occurred '
                                           f'during the processing of the '
                                           f'"attribute_data_post" function.'
                                           f'Error: {str(e)}',
                        })
                        rec.state = "failed"
                if rec.function == "create_order":
                    try:
                        model.create_order(rec.data, rec.instance_id)
                        rec.state = "done"
                    except Exception as e:
                        _logger.info('Some error has been occurred in the '
                                     'processing of function:create_order')
                        number_of_items = len(
                            list(filter(lambda x: isinstance(x, dict),
                                        rec.data)))
                        self.env['woo.logs'].sudo().create([{
                            'status': 'failed',
                            'trigger': 'import',
                            'description': f'An exception error occurred '
                                           f'during the processing of the '
                                           f'"create_order" function.'
                                           f'{number_of_items}'
                                           f' Orders failed to Import.'
                                           f' Error: {str(e)}',
                        }])
                        rec.state = "failed"
                if rec.function == "order_data_post":
                    try:
                        model.order_data_post(rec.data, rec.instance_id)
                        rec.state = "done"
                    except Exception as e:
                        _logger.info('Some error has been occurred in the'
                                     ' processing of function:create_order')
                        self.env['woo.logs'].sudo().create([{
                            'status': 'failed',
                            'trigger': 'export',
                            'description': f'An exception error occurred '
                                           f'during the processing of the '
                                           f'"order_data_post" function.'
                                           f'Error: {str(e)}',
                        }])
                        rec.state = "failed"
                # Sync all button
                if rec.function == "write_customer":
                    try:
                        model.write_customer(rec.data, rec.instance_id)
                        rec.state = "done"
                    except Exception as e:
                        _logger.info(
                            'Some error has been occurred in the processing'
                            ' of function:write_customer')
                        number_of_items = len(
                            list(filter(lambda x: isinstance(x, dict),
                                        rec.data)))
                        self.env['woo.logs'].sudo().create([{
                            'status': 'failed',
                            'trigger': 'import',
                            'description': f'An exception error occurred '
                                           f'during the processing of the '
                                           f'"write_customer" function.'
                                           f'{number_of_items}'
                                           f' Customers failed to Sync.'
                                           f' Error: {str(e)}',
                        }])
                        rec.state = "failed"
                if rec.function == "write_product_data":
                    try:
                        number_of_items = len(
                            list(filter(lambda x: isinstance(x, dict),
                                        rec.data)))
                        model.write_product_data(rec.data, rec.instance_id)
                        rec.state = "done"
                    except Exception as e:
                        _logger.info(
                            'Some error has been occurred in the processing'
                            ' of function:write_product_data')
                        number_of_items = len(
                            list(filter(lambda x: isinstance(x, dict),
                                        rec.data)))
                        self.env['woo.logs'].sudo().create([{
                            'status': 'failed',
                            'trigger': 'import',
                            'description': f'An exception error occurred '
                                           f'during the processing of the '
                                           f'"write_product_data" function.'
                                           f'{number_of_items}'
                                           f'Products  failed to Sync.'
                                           f' Error: {str(e)}',
                        }])
                        rec.state = "failed"
                if rec.function == "write_order_data":
                    try:
                        model.write_order_data(rec.data, rec.instance_id)
                        rec.state = "done"
                    except Exception as e:
                        _logger.info(
                            'Some error has been occurred in the processing'
                            ' of function:write_order_data')
                        number_of_items = len(
                            list(filter(lambda x: isinstance(x, dict),
                                        rec.data)))
                        self.env['woo.logs'].sudo().create([{
                            'status': 'failed',
                            'trigger': 'import',
                            'description': f'An exception error occurred '
                                           f'during the processing of the '
                                           f'"write_order_data" function.'
                                           f'{number_of_items}'
                                           f' Orders failed to Sync.'
                                           f' Error: {str(e)}',
                        }])
                        rec.state = "failed"
