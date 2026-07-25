# -*- coding: utf-8 -*-
import logging
import os

from odoo import Command
from odoo.exceptions import AccessError
from odoo.modules.module import get_module_path
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'optical_crm_followup')
class TestFondations(TransactionCase):
    """Story 15.0 — Fondations techniques du module optical_crm_followup."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.group_optical_user = cls.env.ref('optical.group_optical_user')
        cls.group_optical_manager = cls.env.ref('optical.group_optical_manager')

        base_group = cls.env.ref('base.group_user').id
        group_all_ou = cls.env.ref(
            'operating_unit_access_all.group_all_operating_unit',
            raise_if_not_found=False,
        )
        base_groups = [base_group]
        if group_all_ou:
            base_groups.append(group_all_ou.id)

        # Deux boutiques distinctes pour tester l'isolation multi-boutique
        cls.warehouse_vdn = cls.env['stock.warehouse'].create({
            'name': 'Boutique VDN',
            'code': 'VDN',
        })
        cls.warehouse_corniche = cls.env['stock.warehouse'].create({
            'name': 'Boutique Corniche',
            'code': 'CORN',
        })

        # Commercial rattaché à VDN uniquement
        cls.user_commercial_a = cls.env['res.users'].with_context(
            no_reset_password=True
        ).create({
            'name': 'Commercial A (VDN)',
            'login': 'commercial_a_vdn',
            'email': 'a@test.com',
            'groups_id': [Command.set([cls.group_optical_user.id] + base_groups)],
            'optical_warehouse_ids': [Command.set([cls.warehouse_vdn.id])],
        })

        # Commercial rattaché à Corniche uniquement
        cls.user_commercial_b = cls.env['res.users'].with_context(
            no_reset_password=True
        ).create({
            'name': 'Commercial B (Corniche)',
            'login': 'commercial_b_corn',
            'email': 'b@test.com',
            'groups_id': [Command.set([cls.group_optical_user.id] + base_groups)],
            'optical_warehouse_ids': [Command.set([cls.warehouse_corniche.id])],
        })

        # Responsable (aucun rattachement — doit voir tout via bypass manager)
        cls.user_manager_c = cls.env['res.users'].with_context(
            no_reset_password=True
        ).create({
            'name': 'Responsable C',
            'login': 'manager_c',
            'email': 'c@test.com',
            'groups_id': [Command.set([cls.group_optical_manager.id] + base_groups)],
        })

        # Un patient de test
        cls.partner = cls.env['res.partner'].create({'name': 'Patient Test'})

        # Un calendrier par boutique
        cls.schedule_vdn = cls.env['optical.followup.schedule'].create({
            'name': 'SCH-VDN-001',
            'partner_id': cls.partner.id,
            'warehouse_id': cls.warehouse_vdn.id,
        })
        cls.schedule_corniche = cls.env['optical.followup.schedule'].create({
            'name': 'SCH-CORN-001',
            'partner_id': cls.partner.id,
            'warehouse_id': cls.warehouse_corniche.id,
        })

    # ------------------------------------------------------------------
    # AC1 — Installation propre et dépendances
    # ------------------------------------------------------------------

    def test_module_installs_cleanly(self):
        """Le module optical_crm_followup est installé après la fixture Odoo."""
        module = self.env['ir.module.module'].search(
            [('name', '=', 'optical_crm_followup')], limit=1
        )
        self.assertTrue(module, "Module non trouvé dans ir.module.module")
        self.assertEqual(module.state, 'installed')
        declared = set(module.dependencies_id.mapped('name'))
        # Aucune dépendance à crm/gamification/operating_unit
        self.assertNotIn('crm', declared)
        self.assertNotIn('gamification', declared)
        self.assertNotIn('operating_unit', declared)
        # Toutes les dépendances requises par l'architecture V1.1 sont présentes (L5)
        for required in ('optical', 'sale_management', 'stock', 'mail', 'helpdesk_mgmt'):
            self.assertIn(
                required, declared,
                "Dépendance requise manquante dans le manifest : %s" % required,
            )

    # ------------------------------------------------------------------
    # AC2 — Aucun nouveau groupe créé
    # ------------------------------------------------------------------

    def test_no_new_group_created(self):
        """Aucun res.groups n'est déclaré par optical_crm_followup lui-même."""
        module = self.env['ir.module.module'].search(
            [('name', '=', 'optical_crm_followup')], limit=1
        )
        data_records = self.env['ir.model.data'].search([
            ('module', '=', 'optical_crm_followup'),
            ('model', '=', 'res.groups'),
        ])
        self.assertFalse(
            data_records,
            "Aucun res.groups ne doit être défini par optical_crm_followup "
            "(les groupes sont hérités de optical) — trouvés : %s"
            % data_records.mapped('name'),
        )
        # Sanity check : les deux groupes hérités sont bien accessibles
        self.assertTrue(self.env.ref('optical.group_optical_user'))
        self.assertTrue(self.env.ref('optical.group_optical_manager'))

    # ------------------------------------------------------------------
    # AC3 — ACL sur les 6 nouveaux modèles
    # ------------------------------------------------------------------

    def test_acl_user_read_only_on_config(self):
        """Un user standard peut lire les plans mais pas créer/modifier/supprimer."""
        plan = self.env['optical.followup.plan'].create({'name': 'Plan Test User RO'})
        # Read OK
        plan_as_user = plan.with_user(self.user_commercial_a)
        self.assertEqual(plan_as_user.name, 'Plan Test User RO')
        # Create refusé
        with self.assertRaises(AccessError):
            self.env['optical.followup.plan'].with_user(
                self.user_commercial_a
            ).create({'name': 'Ne doit pas créer'})
        # Write refusé
        with self.assertRaises(AccessError):
            plan_as_user.write({'name': 'Ne doit pas modifier'})
        # Unlink refusé
        with self.assertRaises(AccessError):
            plan_as_user.unlink()

    def test_acl_user_readonly_on_all_config_models(self):
        """M1 — user standard : R only sur les 4 modèles de configuration (plan, plan.step, holiday.window, lunar.date)."""
        # Fixtures : un enregistrement par modèle, créé par le manager pour éviter blocage ACL
        plan = self.env['optical.followup.plan'].with_user(
            self.user_manager_c
        ).create({'name': 'Plan Fixture ACL'})
        activity_type_call = self.env.ref('mail.mail_activity_data_call')
        plan_step = self.env['optical.followup.plan.step'].with_user(
            self.user_manager_c
        ).create({
            'plan_id': plan.id,
            'name': 'Étape Fixture ACL',
            'activity_type_id': activity_type_call.id,
        })
        holiday = self.env['optical.followup.holiday.window'].with_user(
            self.user_manager_c
        ).create({
            'name': 'Fixture ACL Ramadan',
            'date_start_civil': '01-01',
            'date_end_civil': '01-02',
        })
        lunar = self.env['optical.followup.lunar.date'].with_user(
            self.user_manager_c
        ).create({
            'name': 'Fixture ACL Ramadan 2099',
            'year': 2099,
            'event': 'ramadan_start',
        })

        cases = [
            ('optical.followup.plan', plan, {'name': 'Modif interdite'}),
            ('optical.followup.plan.step', plan_step, {'name': 'Modif interdite'}),
            ('optical.followup.holiday.window', holiday, {'name': 'Modif interdite'}),
            ('optical.followup.lunar.date', lunar, {'year': 2099}),
        ]
        for model_name, record, write_vals in cases:
            rec_as_user = record.with_user(self.user_commercial_a)
            # Lecture OK
            self.assertTrue(
                rec_as_user.read(),
                "user devrait pouvoir lire %s" % model_name,
            )
            # Write refusé
            with self.assertRaises(
                AccessError,
                msg="user ne doit pas écrire sur %s" % model_name,
            ):
                rec_as_user.write(write_vals)
            # Unlink refusé
            with self.assertRaises(
                AccessError,
                msg="user ne doit pas supprimer sur %s" % model_name,
            ):
                rec_as_user.unlink()

        # Create refusé sur les 4 modèles config
        with self.assertRaises(AccessError):
            self.env['optical.followup.plan'].with_user(
                self.user_commercial_a
            ).create({'name': 'Interdit'})
        with self.assertRaises(AccessError):
            self.env['optical.followup.plan.step'].with_user(
                self.user_commercial_a
            ).create({'plan_id': plan.id, 'name': 'Interdit'})
        with self.assertRaises(AccessError):
            self.env['optical.followup.holiday.window'].with_user(
                self.user_commercial_a
            ).create({'name': 'Interdit'})
        with self.assertRaises(AccessError):
            self.env['optical.followup.lunar.date'].with_user(
                self.user_commercial_a
            ).create({
                'name': 'Interdit',
                'year': 2099,
                'event': 'aid_fitr',
            })

    def test_acl_user_rw_on_schedule_no_create_no_unlink(self):
        """M1 — user : RW sur schedule + schedule.line, mais Create et Unlink refusés (matrice AC3)."""
        # Ligne existante sur le calendrier VDN (visible du commercial A)
        line = self.env['optical.followup.schedule.line'].create({
            'schedule_id': self.schedule_vdn.id,
        })

        # Écriture OK sur schedule visible
        self.schedule_vdn.with_user(self.user_commercial_a).write(
            {'state': 'paused'}
        )
        # Écriture OK sur schedule.line visible
        line.with_user(self.user_commercial_a).write({'sequence': 20})

        # Create refusé (perm_create=0 côté ACL user)
        with self.assertRaises(AccessError):
            self.env['optical.followup.schedule'].with_user(
                self.user_commercial_a
            ).create({
                'name': 'Interdit',
                'partner_id': self.partner.id,
                'warehouse_id': self.warehouse_vdn.id,
            })
        with self.assertRaises(AccessError):
            self.env['optical.followup.schedule.line'].with_user(
                self.user_commercial_a
            ).create({'schedule_id': self.schedule_vdn.id})

        # Unlink refusé (perm_unlink=0 côté ACL user, aligné avec la record rule L2)
        with self.assertRaises(AccessError):
            self.schedule_vdn.with_user(self.user_commercial_a).unlink()
        with self.assertRaises(AccessError):
            line.with_user(self.user_commercial_a).unlink()

    def test_acl_manager_full_access_on_config(self):
        """Un manager peut créer, modifier, supprimer sur tous les modèles config."""
        plan = self.env['optical.followup.plan'].with_user(
            self.user_manager_c
        ).create({'name': 'Plan Manager Full'})
        plan.write({'name': 'Plan Manager Full (modifié)'})
        plan.unlink()

        hw = self.env['optical.followup.holiday.window'].with_user(
            self.user_manager_c
        ).create({
            'name': 'Ramadan Test',
            'date_start_civil': '01-01',
            'date_end_civil': '01-02',
        })
        hw.write({'name': 'Ramadan Test 2'})
        hw.unlink()

        ld = self.env['optical.followup.lunar.date'].with_user(
            self.user_manager_c
        ).create({
            'name': 'Ramadan 2098',
            'year': 2098,
            'event': 'ramadan_start',
        })
        ld.write({'year': 2097})
        ld.unlink()

    # ------------------------------------------------------------------
    # AC4 — Champ optical_warehouse_ids sur res.users
    # ------------------------------------------------------------------

    def test_optical_warehouse_ids_field(self):
        """Le champ many2many optical_warehouse_ids existe et pointe sur stock.warehouse."""
        field = self.env['res.users']._fields.get('optical_warehouse_ids')
        self.assertIsNotNone(field, "Champ optical_warehouse_ids absent de res.users")
        self.assertEqual(field.comodel_name, 'stock.warehouse')
        self.assertEqual(field.type, 'many2many')
        # Le commercial A est bien rattaché à VDN
        self.assertIn(self.warehouse_vdn, self.user_commercial_a.optical_warehouse_ids)

    # ------------------------------------------------------------------
    # AC5 — Record rules multi-boutique
    # ------------------------------------------------------------------

    def test_record_rule_isolates_warehouses(self):
        """Un commercial VDN ne voit pas les calendriers de Corniche."""
        schedules_visible = self.env['optical.followup.schedule'].with_user(
            self.user_commercial_a
        ).search([])
        self.assertIn(self.schedule_vdn, schedules_visible)
        self.assertNotIn(self.schedule_corniche, schedules_visible)

        # Accès direct par ID au calendrier Corniche → AccessError
        with self.assertRaises(AccessError):
            self.env['optical.followup.schedule'].with_user(
                self.user_commercial_a
            ).browse(self.schedule_corniche.id).read(['name'])

    def test_record_rule_manager_sees_all(self):
        """Un manager (sans rattachement optical_warehouse_ids) voit tous les calendriers."""
        schedules_visible = self.env['optical.followup.schedule'].with_user(
            self.user_manager_c
        ).search([])
        self.assertIn(self.schedule_vdn, schedules_visible)
        self.assertIn(self.schedule_corniche, schedules_visible)

    def test_record_rule_on_schedule_line(self):
        """Les lignes de calendrier sont filtrées par la boutique du parent."""
        line_vdn = self.env['optical.followup.schedule.line'].create({
            'schedule_id': self.schedule_vdn.id,
        })
        line_corn = self.env['optical.followup.schedule.line'].create({
            'schedule_id': self.schedule_corniche.id,
        })
        lines_visible = self.env['optical.followup.schedule.line'].with_user(
            self.user_commercial_a
        ).search([])
        self.assertIn(line_vdn, lines_visible)
        self.assertNotIn(line_corn, lines_visible)

    # ------------------------------------------------------------------
    # AC6 — Menu top-level et arborescence
    # ------------------------------------------------------------------

    def test_menu_root_exists_and_gated_user(self):
        """Le menu top-level Fidélisation existe et est visible par group_optical_user."""
        menu = self.env.ref('optical_crm_followup.menu_optical_followup_root')
        self.assertTrue(menu)
        self.assertIn(self.group_optical_user, menu.groups_id)

    def test_menu_visibility_by_group(self):
        """Chaque menuitem déclare explicitement son groups conforme à AC6."""
        expected_user = [
            'optical_crm_followup.menu_optical_followup_root',
            'optical_crm_followup.menu_optical_followup_my_schedules',
            'optical_crm_followup.menu_optical_followup_my_overdue',
        ]
        expected_manager_only = [
            'optical_crm_followup.menu_optical_followup_configuration',
            'optical_crm_followup.menu_optical_followup_plans',
        ]
        # Menus masqués aux managers optiques V1 (2026-07-25) — restreints à
        # base.group_system tant que la fonctionnalité n'est pas demandée par
        # le client. Lors de la restitution : déplacer dans expected_manager_only.
        expected_system_only = [
            'optical_crm_followup.menu_optical_followup_holiday_windows',
            'optical_crm_followup.menu_optical_followup_lunar_dates',
        ]
        group_system = self.env.ref('base.group_system')
        for xml_id in expected_user:
            menu = self.env.ref(xml_id)
            self.assertIn(
                self.group_optical_user, menu.groups_id,
                "Menu %s devrait être accessible à group_optical_user" % xml_id,
            )
        for xml_id in expected_manager_only:
            menu = self.env.ref(xml_id)
            self.assertIn(
                self.group_optical_manager, menu.groups_id,
                "Menu %s devrait être gardé par group_optical_manager" % xml_id,
            )
            self.assertNotIn(
                self.group_optical_user, menu.groups_id,
                "Menu %s ne doit PAS être ouvert à group_optical_user" % xml_id,
            )
        for xml_id in expected_system_only:
            menu = self.env.ref(xml_id)
            self.assertIn(
                group_system, menu.groups_id,
                "Menu %s devrait être restreint à base.group_system" % xml_id,
            )
            self.assertNotIn(
                self.group_optical_manager, menu.groups_id,
                "Menu %s ne doit PAS être ouvert au manager optique tant "
                "que la fonctionnalité n'est pas restituée" % xml_id,
            )

    # ------------------------------------------------------------------
    # AC7 — Fichier i18n/fr.po
    # ------------------------------------------------------------------

    def test_i18n_fr_po_present(self):
        """Le fichier i18n/fr.po est présent dans le module au commit."""
        module_path = get_module_path('optical_crm_followup')
        self.assertTrue(module_path, "Chemin du module introuvable")
        po_path = os.path.join(module_path, 'i18n', 'fr.po')
        self.assertTrue(
            os.path.isfile(po_path),
            "Fichier i18n/fr.po manquant à %s" % po_path,
        )
        with open(po_path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('optical_crm_followup', content)
        self.assertIn('Fidélisation', content)

    # ------------------------------------------------------------------
    # AC8 — Hook post_init : warning si users non rattachés
    # ------------------------------------------------------------------

    def test_post_init_warning_when_users_not_linked(self):
        """Le hook post_init log un warning si des vendeurs n'ont pas de boutique."""
        from odoo.addons.optical_crm_followup.hooks import post_init_hook

        # Créer un vendeur sans rattachement
        base_groups = [self.env.ref('base.group_user').id]
        group_all_ou = self.env.ref(
            'operating_unit_access_all.group_all_operating_unit',
            raise_if_not_found=False,
        )
        if group_all_ou:
            base_groups.append(group_all_ou.id)
        self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Vendeur Non Rattaché',
            'login': 'vendeur_sans_boutique',
            'email': 'orphan@test.com',
            'groups_id': [Command.set([self.group_optical_user.id] + base_groups)],
        })

        with self.assertLogs(
            'odoo.addons.optical_crm_followup.hooks', level='WARNING'
        ) as cm:
            post_init_hook(self.env)
        joined = '\n'.join(cm.output)
        self.assertIn('vendeur_sans_boutique', joined)
        self.assertIn('optical_warehouse_ids', joined)

    def test_post_init_hook_ignores_managers(self):
        """L4 — le filtre .filtered() du hook exclut bien les managers sans rattachement.

        Test de la logique métier directement (indépendant du système de logging Odoo).
        Reproduit la recherche + filtre du hook et vérifie que manager_c (manager sans
        optical_warehouse_ids) n'est jamais compté comme utilisateur non rattaché.
        """
        group_user = self.env.ref('optical.group_optical_user')
        users_from_search = self.env['res.users'].search([
            ('groups_id', '=', group_user.id),
            ('optical_warehouse_ids', '=', False),
            ('active', '=', True),
        ])
        # manager_c apparaît via implied_ids (manager → user) et n'a pas de rattachement
        self.assertIn(
            self.user_manager_c, users_from_search,
            "manager_c devrait apparaître dans la recherche (group_optical_manager "
            "implique group_optical_user via implied_ids)",
        )
        # commercial_a_vdn et commercial_b_corn ont un rattachement → exclus par la recherche
        self.assertNotIn(self.user_commercial_a, users_from_search)
        self.assertNotIn(self.user_commercial_b, users_from_search)
        # Application du filtre du hook
        filtered = users_from_search.filtered(
            lambda u: not u.has_group('optical.group_optical_manager')
        )
        self.assertNotIn(
            self.user_manager_c, filtered,
            "manager_c doit être filtré du warning (bypass record rule via groupe manager)",
        )
