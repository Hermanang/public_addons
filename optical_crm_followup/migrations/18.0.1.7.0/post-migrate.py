# -*- coding: utf-8 -*-
"""Story 18-1 — post-migration : bascule des données V1 vers les tiers configurables.

S'exécute APRÈS le chargement du nouveau schéma et des données (les records
``tier_standard`` / ``tier_vip`` existent déjà, créés par
``data/optical_customer_tier_data.xml``).

Opérations (toutes idempotentes — AC-6.4) :
  1. Seuil : reprend le seuil VIP V1 (backup pré-migration, ou paramètre système
     encore présent) dans ``tier_vip.threshold_fcfa`` ; nettoie les paramètres.
  2. Plan réservé : ``plan_vip_extra.tier_id = tier_vip`` (le ``noupdate="1"``
     empêche la mise à jour via les données sur une base existante).
  3. Override : ancien booléen ``optical_customer_tier_override`` → M2O
     ``optical_customer_tier_override_id = tier_vip``.
  4. Tier : ancienne Selection ``optical_customer_tier`` → M2O
     ``optical_customer_tier_id`` (``vip`` → tier_vip, sinon tier_standard),
     valeur historique reprise telle quelle (zéro dérive).
  5. Nettoyage schéma : suppression des colonnes V1 orphelines
     (``optical_customer_tier``, ``optical_customer_tier_override``,
     ``vip_only``) — garantit aussi l'idempotence des étapes 3/4.

Chaque lecture d'une colonne V1 est gardée par un test d'existence : après le
premier passage (colonnes supprimées), un rejeu saute silencieusement.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

_V1_PARAM = 'optical_crm_followup.vip_threshold_fcfa'
_BACKUP_PARAM = 'optical_crm_followup.vip_threshold_fcfa_migration_backup'


def _column_exists(cr, table, column):
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})

    tier_standard = env.ref(
        'optical_crm_followup.tier_standard', raise_if_not_found=False,
    )
    tier_vip = env.ref(
        'optical_crm_followup.tier_vip', raise_if_not_found=False,
    )
    if not tier_standard or not tier_vip:
        _logger.error(
            "Migration 18-1 (post) : tiers standard/vip introuvables — "
            "bascule abandonnée (les données de tier n'ont pas été chargées ?)."
        )
        return

    # 1. Seuil VIP V1 → tier_vip.threshold_fcfa (backup pré-migration prioritaire).
    raw = env['ir.config_parameter'].sudo().get_param(_BACKUP_PARAM) \
        or env['ir.config_parameter'].sudo().get_param(_V1_PARAM)
    if raw:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            _logger.warning(
                "Migration 18-1 (post) : seuil VIP V1 mal formé (%r) — seuil "
                "data conservé (%s).", raw, tier_vip.threshold_fcfa,
            )
        else:
            if value > 0:
                tier_vip.threshold_fcfa = value
                _logger.info(
                    "Migration 18-1 (post) : seuil VIP repris de la V1 "
                    "(%s FCFA).", value,
                )
    # Nettoyage des paramètres (le seuil vit désormais sur le tier — AC-5.1).
    env['ir.config_parameter'].sudo().search([
        ('key', 'in', (_V1_PARAM, _BACKUP_PARAM)),
    ]).unlink()

    # 2. plan_vip_extra.tier_id = tier_vip (noupdate a bloqué la MAJ data).
    plan_vip = env.ref(
        'optical_crm_followup.plan_vip_extra', raise_if_not_found=False,
    )
    if plan_vip and not plan_vip.tier_id:
        plan_vip.tier_id = tier_vip
        _logger.info(
            "Migration 18-1 (post) : plan_vip_extra rattaché au tier VIP.",
        )

    # 3. Override booléen V1 → M2O tier_vip.
    if _column_exists(cr, 'res_partner', 'optical_customer_tier_override'):
        cr.execute(
            """
            UPDATE res_partner
            SET optical_customer_tier_override_id = %s
            WHERE optical_customer_tier_override IS TRUE
              AND optical_customer_tier_override_id IS NULL
            """,
            (tier_vip.id,),
        )
        _logger.info(
            "Migration 18-1 (post) : %s partner(s) override VIP migrés vers "
            "le M2O.", cr.rowcount,
        )

    # 4. Selection V1 → M2O (valeur historique reprise telle quelle, sans
    #    garde IS NULL : l'auto-compute initial a pu affecter une valeur
    #    erronée — override/seuil pas encore migrés — la colonne V1 gelée fait
    #    autorité, zéro dérive).
    if _column_exists(cr, 'res_partner', 'optical_customer_tier'):
        cr.execute(
            """
            UPDATE res_partner SET optical_customer_tier_id = %s
            WHERE optical_customer_tier = 'vip'
            """,
            (tier_vip.id,),
        )
        cr.execute(
            """
            UPDATE res_partner SET optical_customer_tier_id = %s
            WHERE optical_customer_tier = 'standard'
               OR optical_customer_tier IS NULL
            """,
            (tier_standard.id,),
        )
        _logger.info(
            "Migration 18-1 (post) : tiers partners migrés (Selection → M2O).",
        )

    # 5. Nettoyage des colonnes V1 orphelines (idempotence des étapes 3/4).
    for table, column in (
        ('res_partner', 'optical_customer_tier'),
        ('res_partner', 'optical_customer_tier_override'),
        ('optical_followup_plan_step', 'vip_only'),
    ):
        if _column_exists(cr, table, column):
            cr.execute(
                'ALTER TABLE "%s" DROP COLUMN "%s"' % (table, column),
            )
            _logger.info(
                "Migration 18-1 (post) : colonne V1 %s.%s supprimée.",
                table, column,
            )
