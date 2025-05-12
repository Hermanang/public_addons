from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _update_filter_values(self):
        def update_filter(product, field_name, field_values, filter_label):
            # Cherche le filtre existant
            filter_rec = self.env['product.filter'].search([('name', '=', filter_label)], limit=1)
            if not filter_rec:
                filter_rec = self.env['product.filter'].create({'name': filter_label, 'type': 'radio'})

            existing_filter_values = filter_rec.filter_value_ids.mapped('name')

            # Crée les nouvelles valeurs du filtre si besoin
            for value in field_values:
                if value not in existing_filter_values:
                    self.env['product.filter.value'].create({
                        'name': value,
                        'filter_id': filter_rec.id,
                    })

            # Identifie les ids des valeurs du filtre à lier
            new_filter_value_ids = filter_rec.filter_value_ids.filtered(lambda f: f.name in field_values).ids

            # Gère les filtres liés au produit
            product_filter = product.filter_ids.filtered(lambda f: f.filter_name_id.name == filter_label)

            if not field_values:
                if product_filter:
                    product_filter.unlink()
            elif not product_filter:
                product.filter_ids.create({
                    'product_tmpl_id': product._origin.id,
                    'filter_name_id': filter_rec.id,
                    'filter_value_ids': [(6, 0, new_filter_value_ids)]
                })
            else:
                product_filter.write({
                    'filter_value_ids': [(6, 0, new_filter_value_ids)]
                })

        filter_fields = self.env['filter.field'].search([('active', '=', True)])
        for product in self:

            for filter_field in filter_fields:
                field = product._fields.get(filter_field.key)
                field_value = getattr(product, filter_field.key)

                if isinstance(field, fields.Selection):
                    # Traitement pour les champs selection
                    field_label = dict(field.selection).get(field_value)
                    field_label_list = [field_label] if field_label is not None else []
                    update_filter(product, filter_field.key, field_label_list, filter_field.name)

                elif isinstance(field, fields.Many2many) or isinstance(field, fields.One2many):
                    # Traitement pour les champs relationnels
                    field_relational_values = field_value.mapped('name')
                    update_filter(product, filter_field.key, field_relational_values, filter_field.name)

    def create(self, vals_list):
        records = super(ProductTemplate, self).create(vals_list)
        records._update_filter_values()
        return records

    def write(self, vals):
        res = super().write(vals)

        filter_fields = self.env['filter.field'].search([('active', '=', True)])
        for filter_field in filter_fields:
            if filter_field.key in vals:
                self._update_filter_values()

        return res

    def pre_init(self):
        return self._update_filter_values()
