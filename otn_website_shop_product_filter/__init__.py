# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from . import models

def post_init_hook(env):
    products = env['product.template'].search([("active", "=", True)])
    for product in products:
        product.pre_init()
