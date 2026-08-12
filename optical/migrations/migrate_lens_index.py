# -*- coding: utf-8 -*-
"""Migration Float → M2O pour product_template.lens_index (Story 19-2).

Appelable depuis pre_init_hook (fresh install) et pre-migrate.py (upgrade).
Idempotente : détecte l'absence de colonne lens_index Float et skippe.
"""
import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


def pre_migrate_lens_index_float_to_m2o(cr):
    """Migre product_template.lens_index (Float) vers optical.lens.index (M2O).

    Étapes idempotentes :
    1. Skip si colonne lens_index Float absente
    2. CREATE TABLE IF NOT EXISTS optical_lens_index
    3. INSERT DISTINCT lens_index > 0 (avec ON CONFLICT DO NOTHING)
    4. ADD COLUMN IF NOT EXISTS lens_index_id integer sur product_template
    5. UPDATE product_template SET lens_index_id via join
    6. DROP COLUMN IF EXISTS lens_index
    """
    if not openupgrade.column_exists(cr, 'product_template', 'lens_index'):
        _logger.info(
            "optical migrate_lens_index: colonne lens_index absente — skip"
        )
        return

    _logger.info("--- optical migrate_lens_index: Float -> M2O ---")

    # Étape 1 : table optical_lens_index (créée avant ORM)
    cr.execute("""
        CREATE TABLE IF NOT EXISTS optical_lens_index (
            id serial PRIMARY KEY,
            name varchar NOT NULL,
            value double precision NOT NULL,
            sequence integer DEFAULT 10,
            active boolean DEFAULT true,
            create_uid integer,
            create_date timestamp,
            write_uid integer,
            write_date timestamp
        )
    """)
    # Contrainte unique séparée (pattern openupgrade — évite doublon si constraint pré-existe)
    # Rattrape `duplicate_table` (contrainte backée par un index unique du même nom)
    # ET `duplicate_object` (contrainte de même nom déjà attachée)
    cr.execute("""
        DO $$ BEGIN
            ALTER TABLE optical_lens_index
                ADD CONSTRAINT optical_lens_index_value_uniq UNIQUE (value);
        EXCEPTION
            WHEN duplicate_table THEN NULL;
            WHEN duplicate_object THEN NULL;
        END $$
    """)

    # Étape 2 : insertion DISTINCT (idempotent via ON CONFLICT)
    # Format `FM990.00` : force 2 décimales (« 1.60 » et non « 1.6 ») — cadrage Q6
    openupgrade.logged_query(cr, """
        INSERT INTO optical_lens_index (name, value)
        SELECT to_char(lens_index, 'FM990.00'), lens_index
        FROM product_template
        WHERE lens_index > 0
        GROUP BY lens_index
        ON CONFLICT (value) DO NOTHING
    """)

    # Étape 3 : colonne lens_index_id sur product_template
    cr.execute("""
        ALTER TABLE product_template
        ADD COLUMN IF NOT EXISTS lens_index_id integer
    """)

    # Étape 4 : peuplement lens_index_id via join
    openupgrade.logged_query(cr, """
        UPDATE product_template pt
        SET lens_index_id = oli.id
        FROM optical_lens_index oli
        WHERE oli.value = pt.lens_index
          AND pt.lens_index > 0
          AND pt.lens_index_id IS NULL
    """)

    # Étape 5 : drop de la vue SQL dépendante (recréée par optical_sale_report.init()
    # au chargement du modèle avec la nouvelle jointure LEFT JOIN optical_lens_index)
    _logger.info(
        "optical migrate_lens_index: DROP VIEW optical_sale_report "
        "(sera recréée par init() du modèle avec la nouvelle jointure)"
    )
    cr.execute("DROP VIEW IF EXISTS optical_sale_report")

    # Étape 6 : drop de la colonne Float (le champ Python ne l'a plus)
    cr.execute("ALTER TABLE product_template DROP COLUMN IF EXISTS lens_index")

    _logger.info("--- optical migrate_lens_index: terminé ---")
