# -*- coding: utf-8 -*-
"""Pre-migration otn_optical → optical : renommage tables et colonnes.

S'execute AVANT le chargement des modeles ORM lors d'un -u optical.
Delegue au module partage migrate_otn_optical.
"""
import logging
import sys
import os

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Pre-migration: renommage tables attributs, colonnes, ir_model_data."""
    if not version:
        return

    _logger.info("=== optical pre-migrate %s ===", version)

    # Ajouter le chemin du module pour importer le module partage
    module_path = os.path.join(os.path.dirname(__file__), '..', '..')
    module_path = os.path.normpath(module_path)
    if module_path not in sys.path:
        sys.path.insert(0, module_path)

    try:
        from migrations.migrate_otn_optical import pre_migrate_from_otn
        pre_migrate_from_otn(cr)
    except ImportError:
        _logger.warning(
            "Impossible d'importer migrate_otn_optical — "
            "migration pre-init probablement deja executee via hook"
        )

    _logger.info("=== optical pre-migrate %s termine ===", version)
