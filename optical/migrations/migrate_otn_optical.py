# -*- coding: utf-8 -*-
"""Fonctions de migration partagées otn_optical → optical.

Appelables depuis pre_init_hook (installation) et pre-migrate.py (upgrade).
Utilise openupgradelib (OCA) pour les operations standard, SQL direct uniquement
quand aucun helper n'existe (ex: ALTER COLUMN TYPE avec USING custom).
"""
import logging

from psycopg2 import sql
from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Story 11-1 : Tables attributs
# ---------------------------------------------------------------------------

ATTRIBUTE_TABLES = [
    ('product_frame_color', 'optical_frame_color'),
    ('product_frame_material', 'optical_frame_material'),
    ('product_frame_usage', 'optical_frame_usage'),
    ('product_lens_treatment', 'optical_lens_treatment'),
    ('product_lens_tint', 'optical_lens_tint'),
]

M2M_TABLE_RENAMES = [
    (
        'product_template_product_frame_material_rel',
        'product_template_optical_frame_material_rel',
    ),
    (
        'product_template_product_frame_color_rel',
        'product_template_optical_frame_color_rel',
    ),
    (
        'product_template_product_frame_usage_rel',
        'product_template_optical_frame_usage_rel',
    ),
    (
        'product_template_product_lens_treatment_rel',
        'product_template_optical_lens_treatment_rel',
    ),
    (
        'product_template_product_lens_tint_rel',
        'product_template_optical_lens_tint_rel',
    ),
]

M2M_COLUMN_SPEC = {
    'product_template_optical_frame_material_rel': [
        ('product_frame_material_id', 'optical_frame_material_id'),
    ],
    'product_template_optical_frame_color_rel': [
        ('product_frame_color_id', 'optical_frame_color_id'),
    ],
    'product_template_optical_frame_usage_rel': [
        ('product_frame_usage_id', 'optical_frame_usage_id'),
    ],
    'product_template_optical_lens_treatment_rel': [
        ('product_lens_treatment_id', 'optical_lens_treatment_id'),
    ],
    'product_template_optical_lens_tint_rel': [
        ('product_lens_tint_id', 'optical_lens_tint_id'),
    ],
}

TYPE_MAPPING = [
    ('frames', 'frame'),
    ('lenses', 'lens'),
    ('contact_lenses', 'contact_lens'),
    ('others', 'accessory'),
]

MODEL_MAPPING = [
    ('product.frame.color', 'optical.frame.color'),
    ('product.frame.material', 'optical.frame.material'),
    ('product.frame.usage', 'optical.frame.usage'),
    ('product.lens.treatment', 'optical.lens.treatment'),
    ('product.lens.tint', 'optical.lens.tint'),
    # product.lens.type n'est PAS renommé : ce modèle n'existe pas comme
    # optical.lens.* dans le code Python.
    # product.lens.thickness : le modèle cible optical.lens.thickness existe
    # depuis Story 19-1, mais on ne renomme PAS la table legacy — les données
    # sont volontairement abandonnées (perte acceptable validée en Story 11-1).
    # Les tables et ir_model_data legacy sont nettoyés dans cleanup_orphan_tables()
    # et le modèle optical.lens.thickness est créé vide par Odoo à l'install/upgrade.
]


# ---------------------------------------------------------------------------
# Story 11-2 : Mesures prescriptions
# ---------------------------------------------------------------------------

EP_COLUMN_RENAMES = {
    'optical_prescription': [
        ('ep_od', 'od_pd'),
        ('ep_og', 'og_pd'),
        ('ep_gl', 'pd_total'),
    ],
}

CHAR_TO_FLOAT_COLUMNS = [
    'od_sphere', 'od_cylinder', 'od_addition', 'od_prism',
    'og_sphere', 'og_cylinder', 'og_addition', 'og_prism',
    'od_pd', 'og_pd', 'pd_total',
]

CHAR_TO_INT_COLUMNS = ['od_axis', 'og_axis']

PRISM_BASE_MAPPING = [
    ('inferior', 'down'),
    ('superior', 'up'),
    ('nasal', 'in'),
    ('temporal', 'out'),
]


# ---------------------------------------------------------------------------
# Post-migration WooCommerce mappings (Story 11-1)
# ---------------------------------------------------------------------------

WOO_MODEL_MAPPING = [
    ('product.frame.material', 'optical.frame.material'),
    ('product.frame.color', 'optical.frame.color'),
    ('product.frame.usage', 'optical.frame.usage'),
    ('product.lens.treatment', 'optical.lens.treatment'),
    ('product.lens.tint', 'optical.lens.tint'),
    ('product.lens.type', 'optical.lens.type'),
    ('product.lens.thickness', 'optical.lens.thickness'),
]


# ---------------------------------------------------------------------------
# Post-migration lens_type → lens_design (Story 11-1)
# ---------------------------------------------------------------------------

LENS_TYPE_TO_DESIGN = {
    'unifocal': 'single_vision',
    'single vision': 'single_vision',
    'simple foyer': 'single_vision',
    'progressif': 'progressive',
    'progressive': 'progressive',
    'bifocal': 'bifocal',
    'degressif': 'degressive',
    'degressive': 'degressive',
    'mi-distance': 'mid_distance',
    'mid distance': 'mid_distance',
}


# ---------------------------------------------------------------------------
# Nettoyage tables orphelines (Story 11-1)
# ---------------------------------------------------------------------------

ORPHAN_TABLES = [
    'product_template_product_lens_type_rel',
    'product_lens_type_product_template_rel',
    'product_template_product_lens_thickness_rel',
    'product_lens_thickness_product_template_rel',
    'product_lens_type',
    'product_lens_thickness',
]


# ---------------------------------------------------------------------------
# Story 11-3 : Nettoyage vues/actions/menus otn_optical avant renommage
# ---------------------------------------------------------------------------

# Modèles UI dont les enregistrements otn_optical doivent être supprimés
# AVANT le renommage module, car les XML IDs sont complètement différents
# entre otn_optical et optical (les vieilles vues inherit pourraient planter).
OTN_UI_MODELS = [
    'ir.ui.menu',
    'ir.actions.act_window',
    'ir.ui.view',
    'ir.actions.report',
]


def cleanup_otn_ui_records(cr):
    """Supprime les vues, actions, menus et rapports otn_optical.

    Doit s'exécuter AVANT update_module_names() pour éviter que les
    vieilles vues inherit ne plantent au chargement du module.
    Le nouveau module optical recrée tout depuis ses propres fichiers XML.
    """
    _logger.info("--- Nettoyage enregistrements UI otn_optical ---")

    # Vérifier que le module otn_optical existe en base
    cr.execute("""
        SELECT id FROM ir_module_module WHERE name = 'otn_optical'
    """)
    if not cr.fetchone():
        _logger.info("Module otn_optical absent (skip)")
        return

    for model in OTN_UI_MODELS:
        table = model.replace('.', '_')

        # Vérifier que la table cible existe (pre_init_hook s'exécute
        # avant le chargement complet — certaines tables UI n'existent
        # pas encore à ce stade)
        if not openupgrade.table_exists(cr, table):
            _logger.info("  %s: table %s absente (skip)", model, table)
            continue

        # Trouver les IDs des enregistrements possédés par otn_optical
        cr.execute("""
            SELECT imd.id, imd.res_id, imd.name
            FROM ir_model_data imd
            WHERE imd.module = 'otn_optical'
              AND imd.model = %s
        """, (model,))
        rows = cr.fetchall()

        if not rows:
            _logger.info("  %s: 0 enregistrements otn_optical (skip)", model)
            continue

        res_ids = [r[1] for r in rows]
        imd_ids = [r[0] for r in rows]

        # Pour ir_ui_view : supprimer d'abord les vues enfants (inherit_id FK)
        # qui référencent les vues à supprimer, puis les vues elles-mêmes.
        if table == 'ir_ui_view':
            cr.execute("""
                WITH RECURSIVE view_tree AS (
                    SELECT id FROM ir_ui_view WHERE id IN %s
                    UNION ALL
                    SELECT v.id FROM ir_ui_view v
                    JOIN view_tree vt ON v.inherit_id = vt.id
                )
                DELETE FROM ir_ui_view WHERE id IN (SELECT id FROM view_tree)
            """, (tuple(res_ids),))
            deleted = cr.rowcount
            # Nettoyer aussi les ir_model_data des vues enfants supprimées
            cr.execute("""
                DELETE FROM ir_model_data
                WHERE model = 'ir.ui.view'
                  AND res_id NOT IN (SELECT id FROM ir_ui_view)
            """)
        else:
            cr.execute(
                sql.SQL("DELETE FROM {} WHERE id IN %s").format(
                    sql.Identifier(table),
                ),
                (tuple(res_ids),)
            )
            deleted = cr.rowcount

        _logger.info("  %s: %d enregistrements supprimés", model, deleted)

        # Supprimer les ir_model_data associes
        cr.execute("""
            DELETE FROM ir_model_data WHERE id IN %s
        """, (tuple(imd_ids),))

    _logger.info("--- Nettoyage UI otn_optical terminé ---")


# XML IDs des vues du nouveau module optical (à conserver).
# MAINTENANCE : cette liste doit être mise à jour à chaque ajout/suppression
# de vue dans les fichiers XML du module optical (views/*.xml).
OPTICAL_VIEW_XMLIDS = [
    'view_order_form_optical', 'view_order_form_optical_lines',
    'view_order_tree_optical', 'res_partner_view_form_optical',
    'res_partner_view_search_optical', 'optical_prescription_view_search',
    'optical_prescription_view_tree', 'optical_prescription_view_form',
    'optical_pec_view_search', 'optical_pec_view_tree', 'optical_pec_view_form',
    'optical_policy_view_search', 'optical_policy_view_tree',
    'optical_policy_view_form', 'optical_insurer_plan_view_search',
    'optical_insurer_plan_view_tree', 'optical_insurer_plan_view_form',
    'optical_coverage_rule_view_tree', 'optical_coverage_rule_view_form',
    'view_move_form_optical', 'view_move_form_optical_send_button',
    'view_account_move_insurance_list', 'view_account_move_insurance_search',
    'view_account_move_tm_list', 'view_account_move_tm_search',
    'view_account_move_aging_list', 'view_account_move_aging_search',
    'view_account_move_aging_pivot',
    'view_optical_claim_sheet_list', 'view_optical_claim_sheet_form',
    'view_optical_claim_sheet_search',
    'optical_lens_treatment_view_list', 'optical_lens_treatment_view_form',
    'optical_lens_tint_view_list', 'optical_lens_tint_view_form',
    'optical_frame_material_view_list', 'optical_frame_material_view_form',
    'optical_frame_color_view_list', 'optical_frame_color_view_form',
    'optical_frame_usage_view_list', 'optical_frame_usage_view_form',
    'optical_product_template_search', 'optical_product_template_list',
    'optical_product_template_form',
]


def cleanup_orphan_optical_views(cr):
    """Supprime les vues orphelines déjà renommées sous module='optical'.

    Cas idempotent : si update_module_names a déjà été exécuté lors d'une
    précédente tentative, les vues otn_optical sont maintenant sous 'optical'.
    On supprime celles dont le XML ID ne correspond pas aux vues du nouveau module.
    """
    _logger.info("--- Nettoyage vues orphelines module optical ---")

    if not openupgrade.table_exists(cr, 'ir_ui_view'):
        _logger.info("  Table ir_ui_view absente (skip)")
        return

    cr.execute("""
        SELECT imd.id, imd.res_id, imd.name
        FROM ir_model_data imd
        WHERE imd.module = 'optical'
          AND imd.model = 'ir.ui.view'
          AND imd.name NOT IN %s
    """, (tuple(OPTICAL_VIEW_XMLIDS),))
    rows = cr.fetchall()

    if not rows:
        _logger.info("  Aucune vue orpheline trouvée (skip)")
        return

    res_ids = [r[1] for r in rows]
    imd_ids = [r[0] for r in rows]
    orphan_names = [r[2] for r in rows]
    _logger.info("  Vues orphelines trouvées: %s", orphan_names)

    # Suppression récursive : inclure les vues enfants (inherit_id FK)
    cr.execute("""
        WITH RECURSIVE view_tree AS (
            SELECT id FROM ir_ui_view WHERE id IN %s
            UNION ALL
            SELECT v.id FROM ir_ui_view v
            JOIN view_tree vt ON v.inherit_id = vt.id
        )
        DELETE FROM ir_ui_view WHERE id IN (SELECT id FROM view_tree)
    """, (tuple(res_ids),))
    _logger.info("  ir_ui_view: %d supprimés", cr.rowcount)

    # Nettoyer ir_model_data des vues orphelines supprimées
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE model = 'ir.ui.view'
          AND res_id NOT IN (SELECT id FROM ir_ui_view)
    """)
    _logger.info("  ir_model_data orphelins: %d supprimés", cr.rowcount)

    _logger.info("--- Nettoyage vues orphelines terminé ---")


# ---------------------------------------------------------------------------
# Main pre-migration entry point
# ---------------------------------------------------------------------------

def pre_migrate_from_otn(cr):
    """Exécute toutes les opérations de pré-migration SQL.

    Appelé depuis pre_init_hook (installation) ou pre-migrate.py (upgrade).
    Idempotent : chaque opération vérifie l'état avant d'agir.
    """
    _logger.info("=== Migration otn_optical -> optical (pre) ===")
    # Story 11-3 : nettoyer les vues/actions/menus otn_optical AVANT renommage
    cleanup_otn_ui_records(cr)
    # Idempotence : nettoyer aussi les vues déjà renommées vers 'optical'
    cleanup_orphan_optical_views(cr)
    # Story 11-1
    migrate_attribute_tables(cr)
    migrate_optical_type(cr)
    migrate_ir_model_data(cr)
    # Story 11-2
    migrate_prescription_measures(cr)
    migrate_partner_flags(cr)
    _logger.info("=== Migration otn_optical -> optical (pre) terminée ===")


# ---------------------------------------------------------------------------
# Migration tables attributs (Story 11-1 AC#1)
# ---------------------------------------------------------------------------

def migrate_attribute_tables(cr):
    """Renomme les 5 tables d'attributs et leurs tables M2M."""
    _logger.info("--- Migration tables attributs ---")

    # Filtrer les tables dont la source existe (idempotence)
    tables_to_rename = [
        (old, new) for old, new in ATTRIBUTE_TABLES
        if openupgrade.table_exists(cr, old)
    ]
    if tables_to_rename:
        openupgrade.rename_tables(cr, tables_to_rename)

    m2m_to_rename = [
        (old, new) for old, new in M2M_TABLE_RENAMES
        if openupgrade.table_exists(cr, old)
    ]
    if m2m_to_rename:
        openupgrade.rename_tables(cr, m2m_to_rename)

    # Renommer les colonnes FK (filtre les tables existantes)
    col_spec = {
        table: cols for table, cols in M2M_COLUMN_SPEC.items()
        if openupgrade.table_exists(cr, table)
    }
    if col_spec:
        openupgrade.rename_columns(cr, col_spec)


# ---------------------------------------------------------------------------
# Migration optical_product_type → optical_type (Story 11-1 AC#2)
# ---------------------------------------------------------------------------

def migrate_optical_type(cr):
    """Renomme la colonne et convertit les valeurs."""
    _logger.info("--- Migration optical_product_type -> optical_type ---")

    if openupgrade.column_exists(cr, 'product_template', 'optical_product_type'):
        openupgrade.rename_columns(cr, {
            'product_template': [('optical_product_type', 'optical_type')],
        })

    if openupgrade.column_exists(cr, 'product_template', 'optical_type'):
        openupgrade.map_values(
            cr,
            source_column='optical_type',
            target_column='optical_type',
            mapping=TYPE_MAPPING,
            table='product_template',
        )


# ---------------------------------------------------------------------------
# Migration ir_model_data (Story 11-1 AC#1)
# ---------------------------------------------------------------------------

def migrate_ir_model_data(cr):
    """Met à jour le module et les références modèle."""
    _logger.info("--- Migration ir_model_data ---")

    # 1. Module otn_optical → optical (gère ir_model_data, ir_translation, deps)
    # merge_modules=True car lors du -i optical, Odoo a déjà créé la row
    # ir_module_module(name='optical') — un simple rename causerait un doublon.
    openupgrade.update_module_names(
        cr, [('otn_optical', 'optical')], merge_modules=True,
    )

    # 2. Renommer les modèles (gère ir_model, ir_model_data, ir_attachment,
    #    mail_message, mail_followers, ir_property, ir_default)
    openupgrade.rename_models(cr, MODEL_MAPPING)


# ---------------------------------------------------------------------------
# Story 11-2 : Conversion mesures prescriptions (AC#1, AC#4)
# ---------------------------------------------------------------------------

def migrate_prescription_measures(cr):
    """Convertit les mesures prescriptions Char → Float/Integer."""
    _logger.info("--- Migration mesures prescriptions ---")
    table = 'optical_prescription'

    if not openupgrade.table_exists(cr, table):
        _logger.info("Table %s introuvable (skip)", table)
        return

    # 1. Renommer colonnes EP → PD (si elles existent)
    ep_cols_to_rename = {
        table: [
            (old, new) for old, new in cols
            if openupgrade.column_exists(cr, table, old)
        ]
        for table, cols in EP_COLUMN_RENAMES.items()
        if openupgrade.table_exists(cr, table)
    }
    ep_cols_to_rename = {t: c for t, c in ep_cols_to_rename.items() if c}
    if ep_cols_to_rename:
        openupgrade.rename_columns(cr, ep_cols_to_rename)

    # 2. Conversion Char → Float (SQL direct — pas de helper openupgradelib
    #    pour ALTER COLUMN TYPE avec expression USING custom)
    for col in CHAR_TO_FLOAT_COLUMNS:
        if not openupgrade.column_exists(cr, table, col):
            continue
        # Vérifier si la colonne est encore en Char (idempotence)
        cr.execute("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        """, (table, col))
        row = cr.fetchone()
        if row and row[0] in ('character varying', 'text'):
            col_id = sql.Identifier(col)
            cr.execute(sql.SQL("""
                ALTER TABLE optical_prescription
                    ALTER COLUMN {} TYPE float8
                    USING CASE
                        WHEN REPLACE(trim({}), ',', '.') ~ '^[+-]?[0-9]*\\.?[0-9]+$'
                        THEN REPLACE(trim({}), ',', '.')::float8
                        ELSE NULL
                    END
            """).format(col_id, col_id, col_id))
            _logger.info("Colonne %s convertie en float8", col)

    # 3. Conversion Char → Integer (axe)
    for col in CHAR_TO_INT_COLUMNS:
        if not openupgrade.column_exists(cr, table, col):
            continue
        cr.execute("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        """, (table, col))
        row = cr.fetchone()
        if row and row[0] in ('character varying', 'text'):
            col_id = sql.Identifier(col)
            cr.execute(sql.SQL("""
                ALTER TABLE optical_prescription
                    ALTER COLUMN {} TYPE integer
                    USING CASE
                        WHEN REPLACE(trim({}), ',', '.') ~ '^[+-]?[0-9]*\\.?[0-9]+$'
                        THEN REPLACE(trim({}), ',', '.')::float8::integer
                        ELSE NULL
                    END
            """).format(col_id, col_id, col_id))
            _logger.info("Colonne %s convertie en integer", col)

    # 4. Conversion valeurs base prisme
    for base_col in ('od_prism_base', 'og_prism_base'):
        if openupgrade.column_exists(cr, table, base_col):
            openupgrade.map_values(
                cr,
                source_column=base_col,
                target_column=base_col,
                mapping=PRISM_BASE_MAPPING,
                table=table,
            )


# ---------------------------------------------------------------------------
# Story 11-2 : Migration flags partenaires (AC#2, AC#4)
# ---------------------------------------------------------------------------

def migrate_partner_flags(cr):
    """Migre is_clinical → is_prescriber et marque les patients."""
    _logger.info("--- Migration flags partenaires ---")
    from odoo.tools import sql as odoo_sql

    # 1. Créer colonnes boolean si absentes (pre-ORM)
    if not openupgrade.column_exists(cr, 'res_partner', 'is_prescriber'):
        odoo_sql.create_column(cr, 'res_partner', 'is_prescriber', 'boolean')
        _logger.info("Colonne créée: res_partner.is_prescriber")
    if not openupgrade.column_exists(cr, 'res_partner', 'is_patient'):
        odoo_sql.create_column(cr, 'res_partner', 'is_patient', 'boolean')
        _logger.info("Colonne créée: res_partner.is_patient")

    # 2. is_clinical → is_prescriber (is_clinical = colonne ancien module)
    if openupgrade.column_exists(cr, 'res_partner', 'is_clinical'):
        openupgrade.logged_query(cr, """
            UPDATE res_partner SET is_prescriber = true
            WHERE is_clinical = true AND (is_prescriber IS NOT true)
        """)

    # 3. Patients distincts des prescriptions
    if openupgrade.table_exists(cr, 'optical_prescription'):
        openupgrade.logged_query(cr, """
            UPDATE res_partner SET is_patient = true
            WHERE id IN (
                SELECT DISTINCT patient_id
                FROM optical_prescription
                WHERE patient_id IS NOT NULL
            ) AND (is_patient IS NOT true)
        """)


# ---------------------------------------------------------------------------
# Post-migration WooCommerce mappings (Story 11-1 AC#4)
# ---------------------------------------------------------------------------

def migrate_woo_attribute_mappings(cr):
    """Met à jour target_model dans woo_attribute_mapping."""
    _logger.info("--- Migration WooCommerce attribute mappings ---")

    if not openupgrade.table_exists(cr, 'woo_attribute_mapping'):
        _logger.info("Table woo_attribute_mapping introuvable (skip)")
        return

    for old_model, new_model in WOO_MODEL_MAPPING:
        openupgrade.logged_query(cr, """
            UPDATE woo_attribute_mapping
            SET target_model = %s
            WHERE target_model = %s
        """, (new_model, old_model))


# ---------------------------------------------------------------------------
# Post-migration lens_type → lens_design (Story 11-1 AC#3)
# ---------------------------------------------------------------------------

def migrate_lens_type_to_design(cr):
    """Mappe les enregistrements product.lens.type vers lens_design."""
    _logger.info("--- Migration lens_type -> lens_design ---")

    old_table = 'product_lens_type'
    if not openupgrade.table_exists(cr, old_table):
        _logger.info("Table %s introuvable (skip)", old_table)
        return

    # Chercher la table M2M
    m2m_candidates = [
        'product_template_product_lens_type_rel',
        'product_lens_type_product_template_rel',
    ]
    m2m_table = None
    for candidate in m2m_candidates:
        if openupgrade.table_exists(cr, candidate):
            m2m_table = candidate
            break

    if not m2m_table:
        _logger.info("Table M2M lens_type introuvable (skip)")
        return

    # Lire les types existants
    cr.execute(
        sql.SQL("SELECT id, name FROM {}").format(sql.Identifier(old_table))
    )
    lens_types = cr.fetchall()
    _logger.info("lens_type: %d enregistrements trouves", len(lens_types))

    # Déterminer les colonnes FK dans la table M2M
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s
    """, (m2m_table,))
    cols = [row[0] for row in cr.fetchall()]
    fk_type_col = None
    fk_tmpl_col = None
    for col in cols:
        if 'lens_type' in col:
            fk_type_col = col
        elif 'product_template' in col or 'template' in col:
            fk_tmpl_col = col

    if not fk_type_col or not fk_tmpl_col:
        _logger.warning(
            "Colonnes FK introuvables dans %s (colonnes: %s)",
            m2m_table, cols,
        )
        return

    # Mapper chaque type vers lens_design
    mapped_count = 0
    for lt_id, lt_name in lens_types:
        lt_name_lower = (lt_name or '').strip().lower()
        design_value = LENS_TYPE_TO_DESIGN.get(lt_name_lower)

        if design_value:
            cr.execute(sql.SQL("""
                UPDATE product_template pt
                SET lens_design = %s
                FROM {} rel
                WHERE rel.{} = pt.id
                  AND rel.{} = %s
                  AND (pt.lens_design IS NULL OR pt.lens_design = '')
            """).format(
                sql.Identifier(m2m_table),
                sql.Identifier(fk_tmpl_col),
                sql.Identifier(fk_type_col),
            ), (design_value, lt_id))
            if cr.rowcount:
                _logger.info(
                    "lens_type '%s' (id=%d) -> lens_design='%s' (%d produits)",
                    lt_name, lt_id, design_value, cr.rowcount,
                )
                mapped_count += cr.rowcount
        else:
            _logger.info(
                "lens_type '%s' (id=%d) : pas de mapping vers lens_design",
                lt_name, lt_id,
            )

    _logger.info("lens_type -> lens_design: %d produits migrés", mapped_count)

    # Logger les lens_thickness comme non migrés
    if openupgrade.table_exists(cr, 'product_lens_thickness'):
        cr.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(
            sql.Identifier('product_lens_thickness'),
        ))
        thickness_count = cr.fetchone()[0]
        _logger.info(
            "product_lens_thickness: %d enregistrements NON MIGRES (perte acceptable)",
            thickness_count,
        )


# ---------------------------------------------------------------------------
# Nettoyage tables orphelines (Story 11-1 AC#3)
# ---------------------------------------------------------------------------

def cleanup_orphan_tables(cr):
    """Supprime les tables orphelines qui ne correspondent plus à aucun modèle."""
    _logger.info("--- Nettoyage tables orphelines ---")

    for table_name in ORPHAN_TABLES:
        if openupgrade.table_exists(cr, table_name):
            cr.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                sql.Identifier(table_name),
            ))

    # Nettoyer ir_model_data et ir_model pour les modèles supprimés
    openupgrade.logged_query(cr, """
        DELETE FROM ir_model_data
        WHERE model IN ('product.lens.type', 'product.lens.thickness')
    """)
    openupgrade.logged_query(cr, """
        DELETE FROM ir_model
        WHERE model IN ('product.lens.type', 'product.lens.thickness')
    """)


# ---------------------------------------------------------------------------
# Story 11-3 : Constantes
# ---------------------------------------------------------------------------

RELATION_TYPE_LABEL = "souscri"  # Recherche insensible à la casse

OBSOLETE_ACCOUNT_MOVE_COLUMNS = [
    'optical_subscriber_id',
    'optical_insurance_id',
    'optical_prescriber_id',
    'optical_clinic_id',
]

OBSOLETE_EMPTY_TABLES = [
    'optical_insurance_policy',  # Ancienne table police (remplacée par optical_policy)
]

# ---------------------------------------------------------------------------
# Story 11-3 : Marquage assureurs depuis relations partenaires (AC#1)
# CC-2026-03-04: retrait migration policies — conservation flags is_insurer
# ---------------------------------------------------------------------------

def mark_insurers_from_relations(cr):
    """Marque is_insurer=true pour les assureurs détectés via res_partner_relation.

    Les relations 'A souscris chez' identifient les partenaires assureurs
    (right_partner_id). La création de polices optical.policy a été retirée
    (CC-2026-03-04 : données fictives sans valeur métier).
    """
    _logger.info("--- Marquage is_insurer depuis relations partenaires ---")

    if not openupgrade.table_exists(cr, 'res_partner_relation'):
        _logger.info("Table res_partner_relation introuvable (skip)")
        return
    if not openupgrade.table_exists(cr, 'res_partner_relation_type'):
        _logger.info("Table res_partner_relation_type introuvable (skip)")
        return

    # Détecter le relation_type_id pour "A souscris chez"
    cr.execute("""
        SELECT id FROM res_partner_relation_type
        WHERE LOWER(name::text) LIKE %s
           OR LOWER(COALESCE(name_inverse::text, '')) LIKE %s
        LIMIT 1
    """, ('%' + RELATION_TYPE_LABEL + '%', '%' + RELATION_TYPE_LABEL + '%'))
    row = cr.fetchone()
    if not row:
        _logger.info(
            "Aucun type de relation contenant '%s' trouve (skip)",
            RELATION_TYPE_LABEL,
        )
        return
    relation_type_id = row[0]
    _logger.info("Type de relation trouve: id=%d", relation_type_id)

    # Marquer les assureurs distincts avec is_insurer = true
    openupgrade.logged_query(cr, """
        UPDATE res_partner SET is_insurer = true
        WHERE id IN (
            SELECT DISTINCT r.right_partner_id
            FROM res_partner_relation r
            WHERE r.type_id = %s
        ) AND (is_insurer IS NOT true)
    """, (relation_type_id,))
    _logger.info("Assureurs marques is_insurer=true: %d", cr.rowcount)


# ---------------------------------------------------------------------------
# Story 11-3 : Nettoyage colonnes account_move (AC#2, AC#5)
# ---------------------------------------------------------------------------

def cleanup_account_move_columns(cr):
    """Supprime les colonnes obsolètes sur account_move si elles sont vides."""
    _logger.info("--- Nettoyage colonnes obsolètes account_move ---")

    for col in OBSOLETE_ACCOUNT_MOVE_COLUMNS:
        if not openupgrade.column_exists(cr, 'account_move', col):
            _logger.info("Colonne %s absente (skip)", col)
            continue

        cr.execute(
            sql.SQL("SELECT COUNT(*) FROM account_move WHERE {} IS NOT NULL").format(
                sql.Identifier(col),
            )
        )
        non_null_count = cr.fetchone()[0]

        if non_null_count == 0:
            cr.execute(
                sql.SQL("ALTER TABLE account_move DROP COLUMN {}").format(
                    sql.Identifier(col),
                )
            )
            _logger.info("Colonne %s supprimée (0 valeurs)", col)
        else:
            _logger.warning(
                "Colonne %s conservee: %d valeurs non-null trouvées",
                col, non_null_count,
            )


# ---------------------------------------------------------------------------
# Story 11-3 : Suppression tables vides obsoletes (AC#3, AC#5)
# ---------------------------------------------------------------------------

def cleanup_empty_legacy_tables(cr):
    """Supprime les tables legacy vides et nettoie ir_model_data."""
    _logger.info("--- Nettoyage tables legacy vides ---")

    for table_name in OBSOLETE_EMPTY_TABLES:
        if not openupgrade.table_exists(cr, table_name):
            _logger.info("Table %s absente (skip)", table_name)
            continue

        cr.execute(
            sql.SQL("SELECT COUNT(*) FROM {}").format(
                sql.Identifier(table_name),
            )
        )
        row_count = cr.fetchone()[0]

        if row_count == 0:
            cr.execute(
                sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                    sql.Identifier(table_name),
                )
            )
            _logger.info("Table %s supprimée (0 enregistrements)", table_name)

            # Nettoyer ir_model_data associées
            # Dériver le nom du modèle depuis le nom de la table
            model_name = table_name.replace('_', '.')
            openupgrade.logged_query(cr, """
                DELETE FROM ir_model_data
                WHERE model = %s
            """, (model_name,))
            openupgrade.logged_query(cr, """
                DELETE FROM ir_model
                WHERE model = %s
            """, (model_name,))
        else:
            _logger.warning(
                "Table %s conservee: %d enregistrements trouves",
                table_name, row_count,
            )
