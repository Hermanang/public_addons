# -*- coding: utf-8 -*-
"""Tests Story 19-2 — migration lens_index Float → M2O (AC-4).

La migration réelle tourne en pre_init_hook / pre-migrate.py (hors ORM).
Ces tests reconstituent la colonne Float dans un savepoint pour couvrir :
- AC-4.1 + AC-4.3 : idempotence sans colonne (fresh install / ré-upgrade)
- AC-4.4 : 100 % des verres Float > 0 mappés vers lens_index_id, fidélité value
"""
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestLensIndexMigration(OpticalTestCommon):
    """Tests dédiés à la migration lens_index Float → M2O."""

    def test_migration_idempotent_no_column(self):
        """AC-4.1 + AC-4.3 : fonction idempotente quand colonne lens_index Float absente.

        Post-install la colonne n'existe plus → l'appel doit skipper sans
        exception ET sans effet de bord sur `optical_lens_index`.
        """
        from odoo.addons.optical.migrations.migrate_lens_index import (
            pre_migrate_lens_index_float_to_m2o,
        )
        cr = self.env.cr
        cr.execute("SELECT COUNT(*) FROM optical_lens_index")
        count_before = cr.fetchone()[0]

        pre_migrate_lens_index_float_to_m2o(cr)

        cr.execute("SELECT COUNT(*) FROM optical_lens_index")
        count_after = cr.fetchone()[0]
        self.assertEqual(
            count_after, count_before,
            "Sans colonne lens_index Float, la migration ne doit rien insérer",
        )

    def test_migration_maps_all_products_with_float_value(self):
        """AC-4.4 : 100 % des verres Float > 0 mappés + fidélité value ± 0,001.

        Reconstitue la colonne Float dans un savepoint, peuple 3 verres
        (deux à 1.60, un à 1.67), appelle la migration réelle, vérifie :
        - décompte : nb produits `lens_index_id IS NOT NULL` == nb produits Float > 0 avant
        - dédoublonnage : les 2 verres 1.60 pointent le même optical.lens.index
        - fidélité : `oli.value` correspond à ±0,001 près
        - libellé : format « 1.60 » (fix H2 — FM990.00)
        """
        from odoo.addons.optical.migrations.migrate_lens_index import (
            pre_migrate_lens_index_float_to_m2o,
        )
        cr = self.env.cr
        products = self.env['product.template'].create([
            {'name': 'S19-2 Migration Test A', 'optical_type': 'lens'},
            {'name': 'S19-2 Migration Test B', 'optical_type': 'lens'},
            {'name': 'S19-2 Migration Test C', 'optical_type': 'lens'},
        ])
        self.env.flush_all()
        ids_tuple = tuple(products.ids)

        with cr.savepoint():
            cr.execute(
                "ALTER TABLE product_template ADD COLUMN lens_index double precision"
            )
            cr.execute(
                "UPDATE product_template SET lens_index = 1.60 WHERE id IN %s",
                (tuple(products[:2].ids),),
            )
            cr.execute(
                "UPDATE product_template SET lens_index = 1.67 WHERE id = %s",
                (products[2].id,),
            )
            cr.execute(
                "UPDATE product_template SET lens_index_id = NULL WHERE id IN %s",
                (ids_tuple,),
            )
            cr.execute(
                "SELECT COUNT(*) FROM product_template "
                "WHERE lens_index > 0 AND id IN %s",
                (ids_tuple,),
            )
            n_before = cr.fetchone()[0]
            self.assertEqual(n_before, 3)

            pre_migrate_lens_index_float_to_m2o(cr)

            cr.execute(
                "SELECT COUNT(*) FROM product_template "
                "WHERE lens_index_id IS NOT NULL AND id IN %s",
                (ids_tuple,),
            )
            n_after = cr.fetchone()[0]
            self.assertEqual(
                n_after, 3,
                "100 % des verres Float > 0 doivent être mappés vers lens_index_id",
            )

            cr.execute(
                "SELECT id, lens_index_id FROM product_template "
                "WHERE id IN %s ORDER BY id",
                (ids_tuple,),
            )
            rows = dict(cr.fetchall())
            self.assertEqual(
                rows[products[0].id], rows[products[1].id],
                "Deux verres avec la même value Float pointent le même optical.lens.index",
            )
            self.assertNotEqual(
                rows[products[0].id], rows[products[2].id],
                "Deux values Float distinctes pointent deux indices distincts",
            )

            cr.execute(
                "SELECT value, name FROM optical_lens_index WHERE id = %s",
                (rows[products[0].id],),
            )
            value_160, name_160 = cr.fetchone()
            self.assertAlmostEqual(
                value_160, 1.60, places=3,
                msg="AC-4.4 : fidélité value ±0,001 pour 1.60",
            )
            self.assertEqual(
                name_160, '1.60',
                "AC-4.2 + cadrage Q6 : libellé normalisé 2 décimales (FM990.00)",
            )

            cr.execute(
                "SELECT value, name FROM optical_lens_index WHERE id = %s",
                (rows[products[2].id],),
            )
            value_167, name_167 = cr.fetchone()
            self.assertAlmostEqual(value_167, 1.67, places=3)
            self.assertEqual(name_167, '1.67')

    def test_migration_data_integrity(self):
        """AC-4.4 : sémantique API post-migration — value du M2O est fidèle.

        Complète les tests SQL ci-dessus en validant que l'API ORM expose
        correctement `product.lens_index_id.value` et `.name`.
        """
        index = self.env['optical.lens.index'].create({
            'name': '1.60', 'value': 1.60,
        })
        product = self.env['product.template'].create({
            'name': 'Verre Test S19-2',
            'optical_type': 'lens',
            'lens_index_id': index.id,
        })
        self.assertEqual(product.lens_index_id.value, 1.60)
        self.assertEqual(product.lens_index_id.name, '1.60')
