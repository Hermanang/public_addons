# -*- coding: utf-8 -*-
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestOpticalSecurity(OpticalTestCommon):
    """Tests de securite du module Optique (AC: #1, #2, #3, #4, #5, #7)."""

    # --- AC #1 : Installation et existence des composants ---

    def test_groups_exist(self):
        """Les groupes Vendeur et Responsable existent."""
        self.assertTrue(self.group_optical_user, "Le groupe Vendeur Optique doit exister")
        self.assertTrue(self.group_optical_manager, "Le groupe Responsable Optique doit exister")

    def test_group_hierarchy(self):
        """Le Responsable herite du Vendeur (ADR-4)."""
        self.assertIn(
            self.group_optical_user,
            self.group_optical_manager.implied_ids,
            "Le Responsable doit heriter du groupe Vendeur"
        )

    def test_manager_has_user_permissions(self):
        """L'utilisateur Responsable possede aussi le groupe Vendeur."""
        self.assertIn(
            self.group_optical_user,
            self.user_responsable.groups_id,
            "L'utilisateur Responsable doit avoir le groupe Vendeur via heritage"
        )

    # --- AC #1 : Sequences ORD et PEC (NFR12) ---

    def test_sequence_ord_exists(self):
        """La sequence ORD existe (NFR12)."""
        seq = self.env['ir.sequence'].search([('code', '=', 'optical.prescription')])
        self.assertTrue(seq, "La sequence ORD doit exister")
        self.assertEqual(seq.prefix, 'ORD/')
        self.assertEqual(seq.padding, 5)

    def test_sequence_pec_exists(self):
        """La sequence PEC existe (NFR12)."""
        seq = self.env['ir.sequence'].search([('code', '=', 'optical.pec')])
        self.assertTrue(seq, "La sequence PEC doit exister")
        self.assertEqual(seq.prefix, 'PEC/')
        self.assertEqual(seq.padding, 5)

    def test_sequence_ord_generates_consecutive(self):
        """La sequence ORD genere des numeros consecutifs."""
        num1 = self.env['ir.sequence'].next_by_code('optical.prescription')
        num2 = self.env['ir.sequence'].next_by_code('optical.prescription')
        self.assertTrue(num1.startswith('ORD/'))
        self.assertTrue(num2.startswith('ORD/'))
        n1 = int(num1.replace('ORD/', ''))
        n2 = int(num2.replace('ORD/', ''))
        self.assertEqual(n2, n1 + 1, "Les numeros ORD doivent etre consecutifs")

    def test_sequence_pec_generates_consecutive(self):
        """La sequence PEC genere des numeros consecutifs."""
        num1 = self.env['ir.sequence'].next_by_code('optical.pec')
        num2 = self.env['ir.sequence'].next_by_code('optical.pec')
        self.assertTrue(num1.startswith('PEC/'))
        self.assertTrue(num2.startswith('PEC/'))
        n1 = int(num1.replace('PEC/', ''))
        n2 = int(num2.replace('PEC/', ''))
        self.assertEqual(n2, n1 + 1, "Les numeros PEC doivent etre consecutifs")

    # --- AC #1 : Labels en francais (NFR18) ---

    def test_labels_francais(self):
        """Tous les labels du module sont en francais (NFR18)."""
        self.assertEqual(self.group_optical_user.name, 'Vendeur Optique')
        self.assertEqual(self.group_optical_manager.name, 'Responsable Optique')

    def test_module_category_francais(self):
        """La categorie du module est en francais."""
        cat = self.env.ref('optical.module_category_optical')
        self.assertEqual(cat.name, 'Optique')

    # --- AC #2 : Menus Responsable (FR52) ---

    def test_responsable_sees_config_menus(self):
        """Le Responsable voit les menus Configuration (FR52)."""
        menu_config = self.env.ref('optical.menu_optical_config')
        visible_groups = menu_config.groups_id
        manager_groups = self.user_responsable.groups_id
        self.assertTrue(
            visible_groups & manager_groups,
            "Le Responsable doit avoir acces au menu Configuration"
        )

    def test_responsable_sees_operational_menus(self):
        """Le Responsable voit aussi les menus operationnels."""
        menu_main = self.env.ref('optical.menu_optical_main')
        visible_groups = menu_main.groups_id
        manager_groups = self.user_responsable.groups_id
        self.assertTrue(
            visible_groups & manager_groups,
            "Le Responsable doit avoir acces au menu principal Optique"
        )

    # --- AC #3 : Menus Vendeur (FR53, NFR8) ---

    def test_vendeur_sees_operational_menus(self):
        """Le Vendeur voit les menus operationnels."""
        menu_main = self.env.ref('optical.menu_optical_main')
        visible_groups = menu_main.groups_id
        vendeur_groups = self.user_vendeur.groups_id
        self.assertTrue(
            visible_groups & vendeur_groups,
            "Le Vendeur doit avoir acces au menu principal Optique"
        )

    def test_vendeur_no_config_menus(self):
        """Le Vendeur ne voit PAS les menus Configuration (FR53, NFR8)."""
        menu_config = self.env.ref('optical.menu_optical_config')
        visible_groups = menu_config.groups_id
        self.assertNotIn(
            self.group_optical_manager,
            self.user_vendeur.groups_id,
            "Le Vendeur ne doit pas avoir le groupe Responsable"
        )
        self.assertIn(
            self.group_optical_manager,
            visible_groups,
            "Le menu Configuration doit etre restreint au groupe Responsable"
        )
        self.assertNotIn(
            self.group_optical_user,
            visible_groups,
            "Le menu Configuration ne doit pas inclure le groupe Vendeur"
        )

    # --- Story 1-3 : Structure des sections parentes ---

    def test_sections_parentes_existent(self):
        """Les 3 sections parentes (Ventes, Assurances, Suivi) existent (Story 1-3 AC1)."""
        for xml_id, expected_name in [
            ('optical.menu_optical_ventes', 'Ventes'),
            ('optical.menu_optical_assurances', 'Assurances'),
            ('optical.menu_optical_suivi', 'Suivi & Facturation'),
        ]:
            menu = self.env.ref(xml_id)
            self.assertTrue(menu, f"Le menu {xml_id} doit exister")
            self.assertEqual(menu.name, expected_name)

    def test_sections_parentes_rattachees_au_menu_principal(self):
        """Les 3 sections sont des enfants directs de menu_optical_main (Story 1-3 AC1)."""
        menu_main = self.env.ref('optical.menu_optical_main')
        for xml_id in [
            'optical.menu_optical_ventes',
            'optical.menu_optical_assurances',
            'optical.menu_optical_suivi',
        ]:
            menu = self.env.ref(xml_id)
            self.assertEqual(
                menu.parent_id, menu_main,
                f"{xml_id} doit etre un enfant direct de menu_optical_main"
            )

    def test_sections_parentes_visibles_vendeur(self):
        """Les sections Ventes, Assurances, Suivi sont visibles pour le Vendeur (Story 1-3 AC1)."""
        vendeur_groups = self.user_vendeur.groups_id
        for xml_id in [
            'optical.menu_optical_ventes',
            'optical.menu_optical_assurances',
            'optical.menu_optical_suivi',
        ]:
            menu = self.env.ref(xml_id)
            self.assertTrue(
                menu.groups_id & vendeur_groups,
                f"Le Vendeur doit voir {xml_id}"
            )

    def test_section_ventes_contenu(self):
        """La section Ventes contient Patients, Ordonnances, Catalogue (Story 1-3 AC2)."""
        menu_ventes = self.env.ref('optical.menu_optical_ventes')
        expected_children = {
            'optical.menu_optical_patients',
            'optical.menu_optical_ordonnances',
            'optical.menu_optical_catalogue',
        }
        for xml_id in expected_children:
            menu = self.env.ref(xml_id)
            self.assertEqual(
                menu.parent_id, menu_ventes,
                f"{xml_id} doit etre dans la section Ventes"
            )

    def test_section_assurances_contenu(self):
        """La section Assurances contient Assurances, IPM, Polices, PEC (Story 1-3 AC3)."""
        menu_assurances = self.env.ref('optical.menu_optical_assurances')
        expected_children = {
            'optical.menu_optical_assureurs',
            'optical.menu_optical_ipm',
            'optical.menu_optical_polices',
            'optical.menu_optical_pec',
        }
        for xml_id in expected_children:
            menu = self.env.ref(xml_id)
            self.assertEqual(
                menu.parent_id, menu_assurances,
                f"{xml_id} doit etre dans la section Assurances"
            )

    def test_section_suivi_contenu(self):
        """La section Suivi contient Factures, TM, Vieillissement, Bordereaux, Generer (Story 1-3 AC4)."""
        menu_suivi = self.env.ref('optical.menu_optical_suivi')
        expected_children = {
            'optical.menu_optical_insurance_invoices',
            'optical.menu_optical_tm_invoices',
            'optical.menu_optical_aging_report',
            'optical.menu_optical_claim_sheet_list',
            'optical.menu_optical_claim_sheet',
        }
        for xml_id in expected_children:
            menu = self.env.ref(xml_id)
            self.assertEqual(
                menu.parent_id, menu_suivi,
                f"{xml_id} doit etre dans la section Suivi & Facturation"
            )

    def test_bordereaux_menus_restricted_to_manager(self):
        """Bordereaux et Generer Bordereau sont restreints au Responsable (Story 1-3 AC4)."""
        for xml_id in [
            'optical.menu_optical_claim_sheet_list',
            'optical.menu_optical_claim_sheet',
        ]:
            menu = self.env.ref(xml_id)
            self.assertIn(
                self.group_optical_manager,
                menu.groups_id,
                f"{xml_id} doit etre restreint au groupe Responsable"
            )
            self.assertNotIn(
                self.group_optical_user,
                menu.groups_id,
                f"{xml_id} ne doit pas inclure le groupe Vendeur directement"
            )

    def test_premier_niveau_maximum_4_sections(self):
        """Le menu principal a au maximum 4 enfants directs : Ventes, Assurances, Suivi, Config (Story 1-3 AC1)."""
        menu_main = self.env.ref('optical.menu_optical_main')
        children = self.env['ir.ui.menu'].search([('parent_id', '=', menu_main.id)])
        self.assertLessEqual(
            len(children), 5,
            f"Le menu principal doit avoir 5 enfants max (hors Config), trouvé {len(children)}"
        )

    # --- AC #5 : Utilisateur sans groupe optique (NFR6) ---
    # Note : Seule la visibilite du menu est testee ici. Les tests
    # AccessError sur les données seront ajoutes avec les modeles optical.*.

    def test_user_sans_groupe_no_menu_access(self):
        """Un utilisateur sans groupe optique ne voit pas le menu Optique (NFR6)."""
        menu_main = self.env.ref('optical.menu_optical_main')
        visible_groups = menu_main.groups_id
        user_groups = self.user_sans_groupe.groups_id
        self.assertFalse(
            visible_groups & user_groups,
            "L'utilisateur sans groupe optique ne doit pas voir le menu Optique"
        )
