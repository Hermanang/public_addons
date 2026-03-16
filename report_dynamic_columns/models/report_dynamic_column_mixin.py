# -*- coding: utf-8 -*-
from odoo import fields, models


class ReportDynamicColumnMixin(models.AbstractModel):
    _name = 'report.dynamic.column.mixin'
    _description = 'Mixin colonnes dynamiques de rapport'

    # NOTE: Les modèles concrets héritant ce mixin DOIVENT redéfinir ce champ
    # avec une relation table explicite pour éviter les conflits entre modèles.
    # Exemple: report_column_ids = fields.Many2many(
    #     'report.dynamic.column', relation='my_model_dynamic_column_rel',
    #     column1='my_model_id', column2='column_id', string='Colonnes du rapport')
    report_column_ids = fields.Many2many(
        'report.dynamic.column',
        string='Colonnes du rapport',
    )

    def _get_report_type(self):
        """Retourne le type de rapport. À surcharger par le modèle concret."""
        return ''

    def _get_available_columns(self, report_type):
        """Retourne les colonnes actives pour un type de rapport, triées par séquence."""
        return self.env['report.dynamic.column'].search([
            ('report_type', '=', report_type),
            ('active', '=', True),
        ], order='sequence, id')

    def _get_column_value(self, column, record, line=None):
        """Retourne la valeur d'une colonne pour un enregistrement. À surcharger par le bridge."""
        return ''

    def _get_report_column_data(self, records, lines_getter=None):
        """Retourne {columns: [...], rows: [{values: [...]}]} pour le template QWeb.

        :param records: recordset à traiter
        :param lines_getter: fonction(record) → iterable de lignes (optionnel)
        :returns: dict avec 'columns' (list de colonnes) et 'rows' (list de dicts avec 'values')
        """
        report_type = self._get_report_type()
        columns = self.report_column_ids or self._get_available_columns(report_type)
        rows = []
        for record in records:
            if lines_getter:
                lines = lines_getter(record)
                for line in lines:
                    row_values = []
                    for col in columns:
                        row_values.append(self._get_column_value(col, record, line))
                    rows.append({'values': row_values})
            else:
                row_values = []
                for col in columns:
                    row_values.append(self._get_column_value(col, record))
                rows.append({'values': row_values})
        return {
            'columns': columns,
            'rows': rows,
        }
