# -*- coding: utf-8 -*-
"""Story 18-1 — pré-migration : snapshot de l'état V1 avant refonte des tiers.

S'exécute AVANT le chargement du nouveau schéma / des nouvelles données. Son
seul rôle est de figer la valeur du seuil VIP V1 (paramètre système) dans une
clé de sauvegarde dédiée, que ``post-migrate.py`` consommera pour renseigner
``tier_vip.threshold_fcfa``. On évite ainsi toute dépendance à l'ordre de
chargement des données pour retrouver le seuil historique.

Idempotent : rejouable sans effet de bord (upsert sur la clé de backup).
"""
import logging

_logger = logging.getLogger(__name__)

_V1_PARAM = 'optical_crm_followup.vip_threshold_fcfa'
_BACKUP_PARAM = 'optical_crm_followup.vip_threshold_fcfa_migration_backup'


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        "SELECT value FROM ir_config_parameter WHERE key = %s", (_V1_PARAM,),
    )
    row = cr.fetchone()
    if not row or not row[0]:
        _logger.info(
            "Migration 18-1 (pre) : aucun seuil VIP V1 à sauvegarder "
            "(paramètre absent — le défaut data 500 000 FCFA s'appliquera)."
        )
        return
    cr.execute(
        """
        INSERT INTO ir_config_parameter (key, value)
        VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """,
        (_BACKUP_PARAM, row[0]),
    )
    _logger.info(
        "Migration 18-1 (pre) : seuil VIP V1 (%s) sauvegardé pour reprise "
        "sur tier_vip.", row[0],
    )
