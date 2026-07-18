# -*- coding: utf-8 -*-
"""Story 16.2 — Tour JS Odoo natif : vérifie que le menu de supervision
'Calendriers en pause SAV > 30 j' est accessible à un manager et que
la vue liste s'affiche sans erreur JS (rendu bout-en-bout).

Premier tour JS de l'initiative optical_crm_followup — politique de test
étendue (mémoire feedback_e2e_tests_scope) : introduction au fil des
stories métier, pas de rétro-fit.

Pré-requis d'exécution :
  - websocket-client (fourni par PIP_DEPS du Makefile depuis S16.2)
  - Chrome / Chromium (absent de l'image odoo:18 par défaut → test skippé
    localement avec « Chrome executable not found »). Le tour est prêt
    pour un CI équipé (ex. odoo/runbot image ou image custom avec
    apt-get install chromium chromium-driver).
"""
from datetime import date, timedelta

from odoo import Command
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'optical_crm_followup')
class TestS04SavPauseUI(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        group_manager = cls.env.ref('optical.group_optical_manager')
        base_group = cls.env.ref('base.group_user').id
        partner_manager = cls.env.ref('base.group_partner_manager').id
        stock_manager = cls.env.ref('stock.group_stock_manager').id
        sales_manager = cls.env.ref('sales_team.group_sale_manager').id
        group_all_ou = cls.env.ref(
            'operating_unit_access_all.group_all_operating_unit',
            raise_if_not_found=False,
        )
        cls.base_groups = [base_group, partner_manager, stock_manager, sales_manager]
        if group_all_ou:
            cls.base_groups.append(group_all_ou.id)

        cls.warehouse = cls.env['stock.warehouse'].create({
            'name': 'Boutique S04-UI',
            'code': 'S04UI',
        })
        cls.manager = cls.env['res.users'].with_context(
            no_reset_password=True
        ).create({
            'name': 'Manager S04-UI',
            'login': 'manager_s04_ui',
            'password': 'manager_s04_ui',
            'email': 'manager_s04_ui@test.com',
            'groups_id': [Command.set([group_manager.id] + cls.base_groups)],
        })

        # Seed : au moins 1 calendrier en pause SAV > 30 j pour que la vue
        # ne soit pas vide (facultatif — le tour accepte aussi l'empty state).
        partner = cls.env['res.partner'].create({
            'name': 'Client SAV UI',
            'birthdate': date.today() - timedelta(days=int(30 * 365.25)),
        })
        partner.write({'optical_followup_consent': True})
        plan = cls.env.ref('optical_crm_followup.plan_standard_18m')
        schedule = cls.env['optical.followup.schedule'].create({
            'name': 'SCH-S04UI',
            'partner_id': partner.id,
            'warehouse_id': cls.warehouse.id,
            'plan_id': plan.id,
            'delivered_date': date.today() - timedelta(days=60),
            'state': 'paused',
            'pause_reason': 'sav_open',
            'sav_paused_date': date.today() - timedelta(days=45),
        })

    def test_tour_sav_supervision_accessible_for_manager(self):
        """Tour JS : navigation Fidélisation → Vues de supervision →
        Calendriers en pause SAV > 30 j, avec un manager.

        Bénéfice : catch régressions de renommage XML ID menu, disparition
        du sous-menu, ou plantage rendu de la vue tree.
        """
        self.start_tour(
            "/odoo",
            "optical_crm_followup.tour_sav_supervision",
            login="manager_s04_ui",
        )
