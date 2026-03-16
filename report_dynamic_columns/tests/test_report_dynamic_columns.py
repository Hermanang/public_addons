# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestReportDynamicColumn(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Column = cls.env['report.dynamic.column']
        cls.Profile = cls.env['report.dynamic.column.profile']

        cls.col1 = cls.Column.create({
            'name': 'Colonne A',
            'technical_name': 'col_a',
            'report_type': 'test_report',
            'sequence': 20,
            'figure_type': 'text',
            'alignment': 'left',
        })
        cls.col2 = cls.Column.create({
            'name': 'Colonne B',
            'technical_name': 'col_b',
            'report_type': 'test_report',
            'sequence': 10,
            'figure_type': 'monetary',
            'alignment': 'right',
            'is_subtotalable': True,
        })
        cls.col3 = cls.Column.create({
            'name': 'Colonne C',
            'technical_name': 'col_c',
            'report_type': 'test_report',
            'sequence': 30,
            'figure_type': 'date',
            'alignment': 'center',
            'active': False,
        })

    # --- Task 8.2 : Test création colonne avec tous les champs ---

    def test_column_creation(self):
        """Test création d'une colonne avec tous les champs."""
        self.assertEqual(self.col1.name, 'Colonne A')
        self.assertEqual(self.col1.technical_name, 'col_a')
        self.assertEqual(self.col1.report_type, 'test_report')
        self.assertEqual(self.col1.sequence, 20)
        self.assertEqual(self.col1.figure_type, 'text')
        self.assertEqual(self.col1.alignment, 'left')
        self.assertFalse(self.col1.is_subtotalable)
        self.assertTrue(self.col1.active)

    def test_column_defaults(self):
        """Test des valeurs par défaut."""
        col = self.Column.create({
            'name': 'Défauts',
            'technical_name': 'defaults_col',
            'report_type': 'test_report',
        })
        self.assertEqual(col.sequence, 10)
        self.assertEqual(col.figure_type, 'text')
        self.assertEqual(col.alignment, 'left')
        self.assertFalse(col.is_subtotalable)
        self.assertTrue(col.active)

    # --- Task 8.3 : Test contrainte unique (technical_name, report_type) ---

    def test_unique_constraint(self):
        """Test contrainte unique sur (technical_name, report_type)."""
        with self.assertRaises(Exception):
            self.Column.create({
                'name': 'Doublon',
                'technical_name': 'col_a',
                'report_type': 'test_report',
            })

    def test_unique_constraint_different_report_type(self):
        """Test que le même technical_name est autorisé pour un autre report_type."""
        col = self.Column.create({
            'name': 'Autre rapport',
            'technical_name': 'col_a',
            'report_type': 'other_report',
        })
        self.assertTrue(col.id)

    # --- Task 8.4 : Test création profil + contrainte is_default unique ---

    def test_profile_creation(self):
        """Test création d'un profil avec colonnes."""
        profile = self.Profile.create({
            'name': 'Profil Test',
            'report_type': 'test_report',
            'column_ids': [(6, 0, [self.col1.id, self.col2.id])],
            'is_default': True,
        })
        self.assertEqual(profile.name, 'Profil Test')
        self.assertEqual(len(profile.column_ids), 2)
        self.assertTrue(profile.is_default)
        self.assertFalse(profile.partner_id)

    def test_profile_unique_default_constraint(self):
        """Test contrainte : un seul profil par défaut par report_type (sans partner_id)."""
        self.Profile.create({
            'name': 'Profil Default 1',
            'report_type': 'test_report',
            'is_default': True,
        })
        with self.assertRaises(ValidationError):
            self.Profile.create({
                'name': 'Profil Default 2',
                'report_type': 'test_report',
                'is_default': True,
            })

    def test_profile_default_allowed_with_partner(self):
        """Test que is_default avec partner_id ne bloque pas un autre default sans partner."""
        self.Profile.create({
            'name': 'Profil Default Global',
            'report_type': 'test_report',
            'is_default': True,
        })
        partner = self.env['res.partner'].create({'name': 'Partenaire Test'})
        profile_partner = self.Profile.create({
            'name': 'Profil Default Partenaire',
            'report_type': 'test_report',
            'is_default': True,
            'partner_id': partner.id,
        })
        self.assertTrue(profile_partner.id)

    def test_profile_default_different_report_type(self):
        """Test que is_default est autorisé pour un autre report_type."""
        self.Profile.create({
            'name': 'Profil Default A',
            'report_type': 'type_a',
            'is_default': True,
        })
        profile_b = self.Profile.create({
            'name': 'Profil Default B',
            'report_type': 'type_b',
            'is_default': True,
        })
        self.assertTrue(profile_b.id)

    # --- Task 8.5 : Test _get_available_columns() ---

    def test_get_available_columns_order(self):
        """Test que _get_available_columns retourne les colonnes actives triées par séquence."""
        Mixin = self.env['report.dynamic.column.mixin']
        columns = Mixin._get_available_columns('test_report')
        # col3 est inactive, ne doit pas apparaître
        self.assertEqual(len(columns), 2)
        # col2 (seq=10) avant col1 (seq=20)
        self.assertEqual(columns[0], self.col2)
        self.assertEqual(columns[1], self.col1)

    def test_get_available_columns_filters_inactive(self):
        """Test que les colonnes inactives sont filtrées."""
        Mixin = self.env['report.dynamic.column.mixin']
        columns = Mixin._get_available_columns('test_report')
        self.assertNotIn(self.col3, columns)

    def test_get_available_columns_filters_report_type(self):
        """Test que les colonnes sont filtrées par report_type."""
        Mixin = self.env['report.dynamic.column.mixin']
        columns = Mixin._get_available_columns('nonexistent_type')
        self.assertEqual(len(columns), 0)

    # --- Task 8.6 : Test _get_report_column_data() ---

    def test_get_report_column_data_structure(self):
        """Test que _get_report_column_data retourne la bonne structure."""
        Mixin = self.env['report.dynamic.column.mixin']
        # On utilise un recordset vide pour tester la structure
        result = Mixin._get_report_column_data(self.env['res.partner'].browse())
        self.assertIn('columns', result)
        self.assertIn('rows', result)
        self.assertIsInstance(result['rows'], list)

    def test_get_report_column_data_with_records(self):
        """Test _get_report_column_data avec des enregistrements."""
        from unittest.mock import patch

        Mixin = self.env['report.dynamic.column.mixin']
        partners = self.env['res.partner'].create([
            {'name': 'Test Partner 1'},
            {'name': 'Test Partner 2'},
        ])
        with patch.object(type(Mixin), '_get_report_type', return_value='test_report'):
            result = Mixin._get_report_column_data(partners)
        # col2 (seq=10) + col1 (seq=20) — col3 inactive exclue
        self.assertEqual(len(result['columns']), 2)
        self.assertEqual(len(result['rows']), 2)
        # Chaque row a une liste de valeurs de longueur == nombre de colonnes
        for row in result['rows']:
            self.assertIn('values', row)
            self.assertEqual(len(row['values']), 2)

    # --- Review: Tests ACL (AC #7) ---

    def test_acl_user_can_read_column(self):
        """Test que group_user peut lire les colonnes."""
        user = self.env['res.users'].create({
            'name': 'Utilisateur Test',
            'login': 'test_user_rdc',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        col = self.Column.with_user(user).browse(self.col1.id)
        self.assertEqual(col.name, 'Colonne A')

    def test_acl_user_cannot_write_column(self):
        """Test que group_user ne peut pas écrire sur les colonnes."""
        user = self.env['res.users'].create({
            'name': 'Utilisateur Test 2',
            'login': 'test_user_rdc2',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        with self.assertRaises(AccessError):
            self.Column.with_user(user).create({
                'name': 'Interdit',
                'technical_name': 'forbidden',
                'report_type': 'test_report',
            })

    def test_acl_user_can_read_profile(self):
        """Test que group_user peut lire les profils."""
        profile = self.Profile.create({
            'name': 'Profil Lecture',
            'report_type': 'test_report',
        })
        user = self.env['res.users'].create({
            'name': 'Utilisateur Test 3',
            'login': 'test_user_rdc3',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        p = self.Profile.with_user(user).browse(profile.id)
        self.assertEqual(p.name, 'Profil Lecture')

    def test_acl_user_cannot_write_profile(self):
        """Test que group_user ne peut pas écrire sur les profils."""
        user = self.env['res.users'].create({
            'name': 'Utilisateur Test 4',
            'login': 'test_user_rdc4',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        with self.assertRaises(AccessError):
            self.Profile.with_user(user).create({
                'name': 'Interdit',
                'report_type': 'test_report',
            })

    def test_acl_system_full_crud_column(self):
        """Test que group_system a CRUD complet sur les colonnes."""
        admin = self.env.ref('base.user_admin')
        col = self.Column.with_user(admin).create({
            'name': 'Admin Col',
            'technical_name': 'admin_col',
            'report_type': 'test_report',
        })
        col.with_user(admin).write({'name': 'Admin Col Updated'})
        col.with_user(admin).unlink()
