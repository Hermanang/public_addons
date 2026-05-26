# -*- coding: utf-8 -*-
"""Fonctions de migration OU dynamique (Story 11-4).

Crée des Operating Units depuis les warehouses existants et propage
l'OU correcte sur toutes les données transactionnelles.
Toutes les fonctions reçoivent `env` (ORM) sauf mention contraire.
Idempotentes : chaque fonction vérifie l'état avant d'agir.
"""
import logging

from psycopg2 import sql as psql

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Task 2 : Création OUs depuis warehouses (AC#1, AC#7)
# ---------------------------------------------------------------------------

def create_ous_from_warehouses(env):
    """Crée une operating.unit pour chaque warehouse sans OU.

    - name = warehouse.name
    - code = warehouse.code
    - company_id = warehouse.company_id
    - partner_id = warehouse.partner_id
    Idempotent : skip les warehouses qui ont déjà une OU.
    """
    _logger.info("--- Création OUs depuis warehouses ---")

    warehouses = env['stock.warehouse'].search([
        ('operating_unit_id', '=', False),
    ])

    if not warehouses:
        _logger.info("Tous les warehouses ont déjà une OU (skip)")
        return

    cr = env.cr
    for wh in warehouses:
        ou = env['operating.unit'].create({
            'name': wh.name,
            'code': wh.code,
            'company_id': wh.company_id.id,
            'partner_id': wh.partner_id.id if wh.partner_id else wh.company_id.partner_id.id,
        })
        # SQL direct pour contourner la contrainte OCA
        # _check_existing_so_in_wh (sale_stock_operating_unit) qui bloque
        # si des SO existent avec une OU différente
        cr.execute(
            "UPDATE stock_warehouse SET operating_unit_id = %s WHERE id = %s",
            (ou.id, wh.id),
        )
        _logger.info(
            "OU créée: '%s' (code=%s) -> warehouse '%s' (id=%d)",
            ou.name, ou.code, wh.name, wh.id,
        )

    env.invalidate_all()
    _logger.info("--- %d OUs créées ---", len(warehouses))


def assign_ou_to_stock_locations(env):
    """Affecte l'OU du warehouse à ses stock locations enfants.

    Pour chaque warehouse avec OU, met à jour les locations du warehouse
    (lot_stock_id et ses enfants) avec l'operating_unit_id du warehouse.
    SQL direct pour contourner les contraintes OCA :
    - _check_parent_operating_unit (parent doit avoir même OU)
    - _check_warehouse_operating_unit (location doit matcher warehouse)
    """
    _logger.info("--- Affectation OU aux stock locations ---")
    cr = env.cr

    warehouses = env['stock.warehouse'].search([
        ('operating_unit_id', '!=', False),
    ])

    total_updated = 0
    for wh in warehouses:
        ou = wh.operating_unit_id
        # Trouver toutes les locations liées à ce warehouse
        # (lot_stock_id et ses enfants récursifs)
        locations = env['stock.location'].search([
            ('id', 'child_of', wh.lot_stock_id.id),
            '|',
            ('operating_unit_id', '=', False),
            ('operating_unit_id', '!=', ou.id),
        ])
        if locations:
            cr.execute(
                "UPDATE stock_location SET operating_unit_id = %s WHERE id IN %s",
                (ou.id, tuple(locations.ids)),
            )
            total_updated += len(locations)
            _logger.info(
                "Warehouse '%s': %d locations mises à jour -> OU '%s'",
                wh.name, len(locations), ou.name,
            )

    env.invalidate_all()
    _logger.info("--- %d stock locations mises à jour ---", total_updated)


# ---------------------------------------------------------------------------
# Task 3 : Propagation OU sur données transactionnelles (AC#2, #3, #7)
# ---------------------------------------------------------------------------

def propagate_ou_sale_orders(env):
    """Propage l'OU du warehouse sur les sale orders.

    UPDATE sale_order SET operating_unit_id = warehouse.operating_unit_id
    WHERE warehouse_id IS NOT NULL
    Utilise SQL direct pour contourner les contraintes OCA.
    """
    _logger.info("--- Propagation OU sale orders ---")
    cr = env.cr

    cr.execute("""
        UPDATE sale_order so
        SET operating_unit_id = sw.operating_unit_id
        FROM stock_warehouse sw
        WHERE so.warehouse_id = sw.id
          AND sw.operating_unit_id IS NOT NULL
          AND (so.operating_unit_id IS NULL
               OR so.operating_unit_id != sw.operating_unit_id)
    """)
    updated = cr.rowcount
    _logger.info("Sale orders mis à jour: %d", updated)

    # Sync stored related field sur les lignes de vente
    # sale_order_line.operating_unit_id = related('order_id.operating_unit_id', store=True)
    # Le SQL direct sur sale_order ne recalcule pas ce champ
    cr.execute("""
        UPDATE sale_order_line sol
        SET operating_unit_id = so.operating_unit_id
        FROM sale_order so
        WHERE sol.order_id = so.id
          AND (sol.operating_unit_id IS NULL
               OR sol.operating_unit_id != so.operating_unit_id)
    """)
    sol_updated = cr.rowcount
    if sol_updated:
        _logger.info("Sale order lines mises à jour: %d", sol_updated)

    # Logger les SO sans warehouse
    cr.execute("""
        SELECT COUNT(*) FROM sale_order
        WHERE warehouse_id IS NULL
    """)
    no_wh = cr.fetchone()[0]
    if no_wh:
        _logger.warning(
            "%d sale orders sans warehouse_id — OU inchangée", no_wh,
        )

    env.invalidate_all()


def propagate_ou_stock_pickings(env):
    """Propage l'OU du warehouse sur les stock pickings.

    UPDATE stock_picking SET operating_unit_id =
        picking_type_id.warehouse_id.operating_unit_id
    Utilise SQL direct.
    """
    _logger.info("--- Propagation OU stock pickings ---")
    cr = env.cr

    cr.execute("""
        UPDATE stock_picking sp
        SET operating_unit_id = sw.operating_unit_id
        FROM stock_picking_type spt
        JOIN stock_warehouse sw ON spt.warehouse_id = sw.id
        WHERE sp.picking_type_id = spt.id
          AND sw.operating_unit_id IS NOT NULL
          AND (sp.operating_unit_id IS NULL
               OR sp.operating_unit_id != sw.operating_unit_id)
    """)
    updated = cr.rowcount
    _logger.info("Stock pickings mis à jour: %d", updated)

    # Logger les pickings sans lien warehouse
    cr.execute("""
        SELECT COUNT(*) FROM stock_picking sp
        LEFT JOIN stock_picking_type spt ON sp.picking_type_id = spt.id
        LEFT JOIN stock_warehouse sw ON spt.warehouse_id = sw.id
        WHERE sw.operating_unit_id IS NULL
          AND sp.operating_unit_id IS NULL
    """)
    no_wh = cr.fetchone()[0]
    if no_wh:
        _logger.warning(
            "%d stock pickings sans lien warehouse — OU reste NULL", no_wh,
        )

    env.invalidate_all()


# ---------------------------------------------------------------------------
# Task 4 : Affectation OU prescriptions (AC#4, #7)
# ---------------------------------------------------------------------------

def assign_ou_prescriptions(env):
    """Affecte l'OU aux prescriptions en 3 étapes.

    1. Prescriptions liées à un sale order → OU du warehouse du SO
    2. Prescriptions restantes → OU du warehouse dominant du create_uid
    3. Fallback → première OU disponible
    """
    _logger.info("--- Affectation OU prescriptions ---")
    cr = env.cr

    # Identifier les OUs dynamiques (pas "Main Operating Unit")
    # On considère qu'une OU liée à un warehouse est une "vraie" OU
    cr.execute("""
        SELECT DISTINCT sw.operating_unit_id
        FROM stock_warehouse sw
        WHERE sw.operating_unit_id IS NOT NULL
    """)
    warehouse_ou_ids = [row[0] for row in cr.fetchall()]

    if not warehouse_ou_ids:
        _logger.warning("Aucun warehouse avec OU — impossible de propager")
        return

    # Étape 1 : prescriptions liées à un SO avec warehouse
    cr.execute("""
        UPDATE optical_prescription p
        SET operating_unit_id = sw.operating_unit_id
        FROM sale_order so
        JOIN stock_warehouse sw ON so.warehouse_id = sw.id
        WHERE so.prescription_id = p.id
          AND sw.operating_unit_id IS NOT NULL
          AND (p.operating_unit_id IS NULL
               OR p.operating_unit_id NOT IN %s)
    """, (tuple(warehouse_ou_ids),))
    step1 = cr.rowcount
    _logger.info("Étape 1 (via sale order): %d prescriptions", step1)

    # Étape 2 : prescriptions restantes → warehouse dominant du create_uid
    cr.execute("""
        UPDATE optical_prescription p
        SET operating_unit_id = sub.dominant_ou
        FROM (
            SELECT so.create_uid,
                   sw.operating_unit_id AS dominant_ou,
                   ROW_NUMBER() OVER (
                       PARTITION BY so.create_uid
                       ORDER BY COUNT(*) DESC
                   ) AS rn
            FROM sale_order so
            JOIN stock_warehouse sw ON so.warehouse_id = sw.id
            WHERE sw.operating_unit_id IS NOT NULL
            GROUP BY so.create_uid, sw.operating_unit_id
        ) sub
        WHERE sub.create_uid = p.create_uid
          AND sub.rn = 1
          AND (p.operating_unit_id IS NULL
               OR p.operating_unit_id NOT IN %s)
    """, (tuple(warehouse_ou_ids),))
    step2 = cr.rowcount
    _logger.info("Étape 2 (via create_uid dominant): %d prescriptions", step2)

    # Étape 3 : fallback → première OU disponible
    cr.execute("""
        SELECT id FROM operating_unit
        WHERE id IN %s AND active = true
        ORDER BY id LIMIT 1
    """, (tuple(warehouse_ou_ids),))
    fallback_row = cr.fetchone()
    if fallback_row:
        fallback_ou_id = fallback_row[0]
        cr.execute("""
            UPDATE optical_prescription
            SET operating_unit_id = %s
            WHERE operating_unit_id IS NULL
               OR operating_unit_id NOT IN %s
        """, (fallback_ou_id, tuple(warehouse_ou_ids)))
        step3 = cr.rowcount
        if step3:
            _logger.warning(
                "Étape 3 (fallback): %d prescriptions -> OU id=%d",
                step3, fallback_ou_id,
            )
    else:
        step3 = 0

    env.invalidate_all()
    _logger.info(
        "--- Prescriptions mises à jour: %d (étape1=%d, étape2=%d, étape3=%d) ---",
        step1 + step2 + step3, step1, step2, step3,
    )


# ---------------------------------------------------------------------------
# Task 5 : Affectation utilisateurs aux OUs (AC#5, #7)
# ---------------------------------------------------------------------------

def assign_users_to_ous(env):
    """Affecte chaque utilisateur à l'OU de son warehouse dominant.

    Le warehouse dominant est celui qui a le plus de sale orders pour l'utilisateur.
    Les utilisateurs sans SO reçoivent la première OU disponible.
    Ne modifie pas les utilisateurs qui ont déjà une assignation correcte
    (sauf ceux assignés uniquement à "Main Operating Unit").
    """
    _logger.info("--- Affectation utilisateurs aux OUs ---")
    cr = env.cr

    # Identifier les OUs dynamiques liées à des warehouses
    cr.execute("""
        SELECT DISTINCT sw.operating_unit_id
        FROM stock_warehouse sw
        WHERE sw.operating_unit_id IS NOT NULL
    """)
    warehouse_ou_ids = [row[0] for row in cr.fetchall()]

    if not warehouse_ou_ids:
        _logger.warning("Aucun warehouse avec OU — impossible d'assigner")
        return

    # Trouver le warehouse dominant par utilisateur
    cr.execute("""
        SELECT so.create_uid,
               sw.operating_unit_id,
               COUNT(*) as cnt
        FROM sale_order so
        JOIN stock_warehouse sw ON so.warehouse_id = sw.id
        WHERE sw.operating_unit_id IS NOT NULL
        GROUP BY so.create_uid, sw.operating_unit_id
        ORDER BY so.create_uid, cnt DESC
    """)
    rows = cr.fetchall()

    # Garder uniquement le warehouse dominant par utilisateur
    user_dominant_ou = {}
    for uid, ou_id, _cnt in rows:
        if uid not in user_dominant_ou:
            user_dominant_ou[uid] = ou_id

    # Première OU disponible pour fallback
    fallback_ou = env['operating.unit'].browse(warehouse_ou_ids[0])

    # Traiter tous les utilisateurs internes (sauf SUPERUSER)
    internal_users = env['res.users'].search([
        ('share', '=', False),
        ('active', '=', True),
        ('id', '!=', 1),  # SUPERUSER_ID — ne pas modifier l'admin
    ])

    updated = 0
    for user in internal_users:
        ou_id = user_dominant_ou.get(user.id, fallback_ou.id)
        ou = env['operating.unit'].browse(ou_id)

        # Vérifier si l'utilisateur a déjà cette OU
        current_ou_ids = user.operating_unit_ids.ids
        if ou_id in current_ou_ids and user.default_operating_unit_id.id == ou_id:
            continue

        # Ajouter l'OU aux operating_unit_ids (sans retirer les existantes)
        if ou_id not in current_ou_ids:
            user.write({
                'operating_unit_ids': [(4, ou_id)],
            })
        # Définir comme default
        user.write({
            'default_operating_unit_id': ou_id,
        })
        updated += 1
        _logger.info(
            "User '%s' (id=%d) -> OU '%s'", user.login, user.id, ou.name,
        )

    _logger.info("--- %d utilisateurs mis à jour ---", updated)


# ---------------------------------------------------------------------------
# Task 6 : Archivage Main Operating Unit (AC#6, #7)
# ---------------------------------------------------------------------------

def cleanup_main_ou(env):
    """Archive la 'Main Operating Unit' si aucun enregistrement ne la référence.

    Détection : OU qui n'est rattachée à aucun warehouse et dont le nom
    contient 'main' (insensible à la casse), ou la plus petite ID sans warehouse.
    """
    _logger.info("--- Archivage Main Operating Unit ---")
    cr = env.cr

    # Identifier les OUs liées à des warehouses
    cr.execute("""
        SELECT DISTINCT operating_unit_id
        FROM stock_warehouse
        WHERE operating_unit_id IS NOT NULL
    """)
    warehouse_ou_ids = [row[0] for row in cr.fetchall()]

    if not warehouse_ou_ids:
        _logger.info("Aucun warehouse avec OU — skip archivage Main OU")
        return

    # Chercher la "Main Operating Unit"
    main_ou = env['operating.unit'].search([
        ('id', 'not in', warehouse_ou_ids),
        ('active', '=', True),
    ], order='id', limit=1)

    if not main_ou:
        _logger.info("Aucune Main Operating Unit candidate trouvée (skip)")
        return

    _logger.info(
        "Main OU candidate: '%s' (id=%d)", main_ou.name, main_ou.id,
    )

    # Vérifier les références restantes dans les tables principales
    tables_to_check = [
        ('sale_order', 'operating_unit_id'),
        ('stock_picking', 'operating_unit_id'),
        ('account_move', 'operating_unit_id'),
        ('account_move_line', 'operating_unit_id'),
        ('optical_prescription', 'operating_unit_id'),
        ('stock_location', 'operating_unit_id'),
    ]

    remaining_refs = []
    for table, col in tables_to_check:
        cr.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = %s AND column_name = %s
            )
        """, (table, col))
        if not cr.fetchone()[0]:
            continue

        cr.execute(
            psql.SQL("SELECT COUNT(*) FROM {} WHERE {} = %s").format(
                psql.Identifier(table), psql.Identifier(col),
            ),
            (main_ou.id,),
        )
        count = cr.fetchone()[0]
        if count:
            remaining_refs.append((table, count))

    # Vérifier la table M2M utilisateurs-OU
    cr.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'operating_unit_users_rel'
              AND table_schema = 'public'
        )
    """)
    if cr.fetchone()[0]:
        cr.execute("""
            SELECT COUNT(*) FROM operating_unit_users_rel
            WHERE operating_unit_id = %s
        """, (main_ou.id,))
        m2m_count = cr.fetchone()[0]
        if m2m_count:
            remaining_refs.append(('operating_unit_users_rel', m2m_count))

    if remaining_refs:
        _logger.warning(
            "Main OU '%s' conservée — références restantes: %s",
            main_ou.name,
            ', '.join('%s (%d)' % (t, c) for t, c in remaining_refs),
        )
        return

    # Aucune référence : archiver
    main_ou.active = False
    _logger.info(
        "Main OU '%s' (id=%d) archivée (active=False)",
        main_ou.name, main_ou.id,
    )
