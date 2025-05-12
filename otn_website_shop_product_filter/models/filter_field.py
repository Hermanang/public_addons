from odoo import models, fields, api


class FilterField(models.Model):
    _name = 'filter.field'

    name = fields.Char(string='Nom', required=True)
    key = fields.Char(string='Cle', required=True)
    active = fields.Boolean(string='Active', readonly=True)

    def write(self, vals):
        res = super(FilterField, self).write(vals)
        if "active" in vals and vals["active"] == False:
            for record in self:
                delete_filter = self.env['product.filter'].search([('name', '=', record.name)])
                delete_filter_line = self.env['filter.product.line'].search([('filter_name_id', '=', delete_filter.id)])
                if delete_filter:
                    if delete_filter_line:
                        delete_filter_line.unlink()
                    delete_filter.filter_value_ids.unlink()
                    delete_filter.unlink()
        return res