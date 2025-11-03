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


class WooLogs(models.Model):
    """
    Class for the model Woo Logs. Contains fields for the model.
    """
    _name = 'woo.logs'
    _rec_name = 'trigger'
    _description = 'Woo Logs'

    status = fields.Selection(
        selection=[('success', 'Success'),
                   ('failed', 'Failed')], readonly=True, string='Status',
        help='Status of the process done that related to the woo log.')
    description = fields.Text(string='Description', readonly=True,
                              help='Description of the woo log.')
    trigger = fields.Selection(selection=[('queue', 'Queue'),
                                          ('import', 'Import'),
                                          ('export', 'Export')],
                               string='Trigger', readonly=True,
                               help='Type of the function triggered that is'
                                    'related to the woo log.')
