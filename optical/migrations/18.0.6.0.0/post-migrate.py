# -*- coding: utf-8 -*-
"""Post-migration otn_optical → optical.

S'execute APRES le chargement des modeles ORM lors d'un -u optical.
Delegue au module partage migrate_otn_optical.
"""
import logging
import sys
import os

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Post-migration: WooCommerce mappings, lens_type, nettoyage."""
    if not version:
        return

    _logger.info("=== optical post-migrate %s ===", version)

    # Ajouter le chemin du module pour importer le module partage
    module_path = os.path.join(os.path.dirname(__file__), '..', '..')
    module_path = os.path.normpath(module_path)
    if module_path not in sys.path:
        sys.path.insert(0, module_path)

    try:
        from migrations.migrate_otn_optical import (
            migrate_woo_attribute_mappings,
            migrate_lens_type_to_design,
            cleanup_orphan_tables,
            mark_insurers_from_relations,
            cleanup_account_move_columns,
            cleanup_empty_legacy_tables,
        )
        # Story 11-1
        migrate_woo_attribute_mappings(cr)
        migrate_lens_type_to_design(cr)
        cleanup_orphan_tables(cr)
        # Story 11-3 (CC-2026-03-04: marquage assureurs + nettoyage, sans policies)
        mark_insurers_from_relations(cr)
        cleanup_account_move_columns(cr)
        cleanup_empty_legacy_tables(cr)
    except ImportError:
        _logger.warning(
            "Impossible d'importer migrate_otn_optical — "
            "operations post-migration non executées"
        )

    _logger.info("=== optical post-migrate %s termine ===", version)
