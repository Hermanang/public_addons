from odoo import models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def get_product_info_pos(self, price, quantity, pos_config_id):
        res = super().get_product_info_pos(price, quantity, pos_config_id)
        config = self.env['pos.config'].browse(pos_config_id)
        # Warehouses
        warehouse_list = [
            {'id': w.id,
             'name': w.name,
             'available_quantity': self.with_context({'warehouse_id': w.id}).qty_available,
             'forecasted_quantity': self.with_context({'warehouse_id': w.id}).virtual_available,
             'immediately_usable_qty': self.with_context({'warehouse_id': w.id}).immediately_usable_qty,
             'uom': self.uom_name}
            for w in self.env['stock.warehouse'].search([('company_id', '=', config.company_id.id)])]

        if config.picking_type_id.warehouse_id:
            # Sort the warehouse_list, prioritizing config.picking_type_id.warehouse_id
            warehouse_list = sorted(
                warehouse_list,
                key=lambda w: w['id'] != config.picking_type_id.warehouse_id.id
            )

        res['warehouses'] = warehouse_list
        return res