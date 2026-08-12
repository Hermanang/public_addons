# -*- coding: utf-8 -*-
import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pre-init hook : migration otn_optical → optical (Epic 11)
# ---------------------------------------------------------------------------

def pre_init_hook(env):
    """Détecter et migrer les données otn_optical si présentes.

    S'exécute à l'installation du module optical (avant chargement ORM).
    Détecte la présence des anciennes tables product_frame_* (Story 11-1)
    ou de la colonne is_clinical (Story 11-2) et appelle les scripts de migration.
    """
    cr = env.cr
    has_otn_tables = openupgrade.table_exists(cr, 'product_frame_color')
    has_legacy_flags = openupgrade.column_exists(cr, 'res_partner', 'is_clinical')
    has_partner_relations = openupgrade.table_exists(cr, 'res_partner_relation')
    if has_otn_tables or has_legacy_flags:
        _logger.info("optical pre_init_hook: données otn_optical détectées — lancement migration")
        from .migrations.migrate_otn_optical import pre_migrate_from_otn
        pre_migrate_from_otn(cr)
    else:
        _logger.info("optical pre_init_hook: pas de données otn_optical détectées (skip)")
    if has_partner_relations:
        _logger.info("optical pre_init_hook: relations partenaires détectées — migration polices planifiée en post-init")
        # La migration des polices est exécutée en post_init_hook car la table
        # optical_policy n'existe pas encore en pre_init (créée par l'ORM)
    else:
        _logger.info("optical pre_init_hook: pas de relations partenaires détectées (skip)")

    # Story 19-2 : migration lens_index Float → M2O (idempotente)
    from .migrations.migrate_lens_index import pre_migrate_lens_index_float_to_m2o
    pre_migrate_lens_index_float_to_m2o(cr)


# ---------------------------------------------------------------------------


def post_init_hook(env):
    """Story 11-3: Marquer les assureurs et nettoyer les artefacts legacy."""

    # Story 11-3 : Marquage assureurs + nettoyage (si données legacy)
    cr = env.cr
    if openupgrade.table_exists(cr, 'res_partner_relation'):
        _logger.info("optical post_init_hook: marquage assureurs + nettoyage")
        from .migrations.migrate_otn_optical import (
            mark_insurers_from_relations,
            cleanup_account_move_columns,
            cleanup_empty_legacy_tables,
        )
        mark_insurers_from_relations(cr)
        cleanup_account_move_columns(cr)
        cleanup_empty_legacy_tables(cr)
