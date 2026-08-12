# -*- coding: utf-8 -*-
"""Pre-migration 18.0.8.0.0 : lens_index Float → optical.lens.index M2O (Story 19-2).

S'exécute AVANT le chargement des modèles ORM lors d'un -u optical.
Délègue au module partagé migrate_lens_index (idempotent).
"""
import logging
import os
import sys

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    _logger.info("=== optical pre-migrate %s ===", version)

    module_path = os.path.join(os.path.dirname(__file__), '..', '..')
    module_path = os.path.normpath(module_path)
    if module_path not in sys.path:
        sys.path.insert(0, module_path)

    try:
        from migrations.migrate_lens_index import pre_migrate_lens_index_float_to_m2o
        pre_migrate_lens_index_float_to_m2o(cr)
    except ImportError:
        _logger.warning(
            "Impossible d'importer migrate_lens_index — "
            "migration pre-init probablement déjà exécutée via hook"
        )

    _logger.info("=== optical pre-migrate %s terminé ===", version)
