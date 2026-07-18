# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Story 15.0 — Avertir si aucun utilisateur commercial n'est rattaché
    à une boutique via `optical_warehouse_ids`.

    Les record rules multi-boutique filtrent les calendriers sur ce champ.
    Si un vendeur n'a aucune boutique rattachée, il ne verra aucun calendrier.
    L'installation continue quand même (pas d'exception) — c'est un rappel
    à l'administrateur de renseigner la table de rattachement avant activation.
    """
    group_user = env.ref('optical.group_optical_user', raise_if_not_found=False)
    if not group_user:
        return
    users_missing = env['res.users'].search([
        ('groups_id', '=', group_user.id),
        ('optical_warehouse_ids', '=', False),
        ('active', '=', True),
    ])
    users_missing = users_missing.filtered(
        lambda u: not u.has_group('optical.group_optical_manager')
    )
    if users_missing:
        _logger.warning(
            "optical_crm_followup : %d utilisateur(s) commercial(aux) n'ont pas "
            "de rattachement `optical_warehouse_ids`. Les record rules "
            "multi-boutique bloqueront leur accès aux calendriers de suivi. "
            "Rattacher les utilisateurs avant activation. Utilisateurs : %s",
            len(users_missing),
            ', '.join(users_missing.mapped('login')),
        )
    else:
        _logger.info(
            "optical_crm_followup : rattachement utilisateurs / boutiques OK "
            "(aucun utilisateur commercial sans `optical_warehouse_ids`)."
        )

    # Story 17-3 AC-B : rappeler à l'admin que le cron mensuel
    # d'anonymisation est livré INACTIF (défaut D-COMPLIANCE-CRON-DRYRUN).
    monthly_cron = env.ref(
        'optical_crm_followup.ir_cron_optical_followup_monthly_anonymize',
        raise_if_not_found=False,
    )
    if monthly_cron and not monthly_cron.active:
        _logger.warning(
            "optical_crm_followup : cron mensuel d'anonymisation livré "
            "DÉSACTIVÉ (mesure de protection Loi 2008-12 art. 65-71). "
            "Exécutez d'abord `env['res.partner']._anonymize_dry_run()` en "
            "shell pour valider le périmètre, puis activez manuellement le "
            "cron via Techniques → Actions planifiées."
        )
