# -*- coding: utf-8 -*-
"""Post-migration 18.0.1.0.0 : creation OUs dynamique et propagation.

S'execute APRES le chargement des modeles ORM lors d'un -u optical_operating_unit.
Delegue au module partage migrate_ou_dynamic.
"""
import logging
import sys
import os

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Post-migration: creation OUs, propagation, affectation users, cleanup."""
    if not version:
        return

    _logger.info("=== optical_operating_unit post-migrate %s (OU dynamique) ===", version)

    # Ajouter le chemin du module pour importer le module partage
    module_path = os.path.join(os.path.dirname(__file__), '..', '..')
    module_path = os.path.normpath(module_path)
    if module_path not in sys.path:
        sys.path.insert(0, module_path)

    env = api.Environment(cr, SUPERUSER_ID, {})

    # Eviter collision sys.modules si optical/migrations a ete charge avant
    sys.modules.pop('migrations', None)
    sys.modules.pop('migrations.migrate_ou_dynamic', None)

    try:
        from migrations.migrate_ou_dynamic import (
            create_ous_from_warehouses,
            assign_ou_to_stock_locations,
            propagate_ou_sale_orders,
            propagate_ou_stock_pickings,
            assign_ou_prescriptions,
            assign_users_to_ous,
            cleanup_main_ou,
        )

        # Ordre critique — ne pas changer
        create_ous_from_warehouses(env)
        assign_ou_to_stock_locations(env)
        propagate_ou_sale_orders(env)
        propagate_ou_stock_pickings(env)
        assign_ou_prescriptions(env)
        assign_users_to_ous(env)
        cleanup_main_ou(env)
    except ImportError:
        _logger.error(
            "Impossible d'importer migrate_ou_dynamic — MIGRATION INCOMPLETE"
        )
        raise

    _logger.info("=== optical_operating_unit post-migrate %s termine ===", version)
