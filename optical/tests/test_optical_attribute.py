# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestOpticalAttributes(OpticalTestCommon):
    """Tests Story 4.1 — Modèles attributs optiques et configuration."""

    ATTRIBUTE_MODELS = [
        'optical.lens.treatment',
        'optical.lens.tint',
        'optical.frame.material',
        'optical.frame.color',
        'optical.frame.usage',
    ]

    def test_create_all_attributes(self):
        """AC #1, #3 : Création d'un attribut dans chacun des 5 modèles."""
        for model_name in self.ATTRIBUTE_MODELS:
            with self.subTest(model=model_name):
                record = self.env[model_name].create({'name': 'Test Attribut'})
                self.assertTrue(record.id, "L'attribut doit être créé avec succès")
                self.assertEqual(record.name, 'Test Attribut')
                self.assertTrue(record.active, "L'attribut doit être actif par défaut")
                self.assertEqual(record.sequence, 10, "La séquence par défaut doit être 10")

    def test_attribute_ordering(self):
        """AC #4 : Les attributs sont triés par sequence puis par name."""
        for model_name in self.ATTRIBUTE_MODELS:
            with self.subTest(model=model_name):
                Model = self.env[model_name]
                Model.create({'name': 'Zeta', 'sequence': 1})
                Model.create({'name': 'Alpha', 'sequence': 1})
                Model.create({'name': 'Beta', 'sequence': 0})

                records = Model.search([])
                names = records.mapped('name')
                # sequence=0 d'abord (Beta), puis sequence=1 triés par name (Alpha, Zeta)
                self.assertEqual(names[0], 'Beta', "Sequence 0 doit apparaître en premier")
                idx_alpha = names.index('Alpha')
                idx_zeta = names.index('Zeta')
                self.assertLess(idx_alpha, idx_zeta,
                                "Alpha doit apparaître avant Zeta (même séquence, tri par name)")

    def test_attribute_archive(self):
        """AC #5 : Un attribut archivé n'apparaît pas dans la recherche par défaut."""
        for model_name in self.ATTRIBUTE_MODELS:
            with self.subTest(model=model_name):
                Model = self.env[model_name]
                record = Model.create({'name': 'Attribut Archivable'})
                record.active = False

                # Recherche par défaut filtre active=True
                visible = Model.search([('name', '=', 'Attribut Archivable')])
                self.assertFalse(visible, "Un attribut archivé ne doit pas apparaître par défaut")

                # Recherche avec active_test=False montre l'attribut
                all_records = Model.with_context(active_test=False).search(
                    [('name', '=', 'Attribut Archivable')]
                )
                self.assertTrue(all_records, "L'attribut archivé doit exister dans la base")

    def test_acl_vendeur_readonly(self):
        """AC #6 : Le vendeur ne peut pas créer, modifier ou supprimer d'attributs."""
        for model_name in self.ATTRIBUTE_MODELS:
            with self.subTest(model=model_name):
                Model = self.env[model_name].with_user(self.user_vendeur)

                # Lecture autorisée
                Model.search([])

                # Création interdite
                with self.assertRaises(AccessError):
                    Model.create({'name': 'Interdit'})

                # Créer un enregistrement en admin pour tester write/unlink
                record = self.env[model_name].create({'name': 'Test Write'})

                # Modification interdite
                with self.assertRaises(AccessError):
                    record.with_user(self.user_vendeur).write({'name': 'Modifié'})

                # Suppression interdite
                with self.assertRaises(AccessError):
                    record.with_user(self.user_vendeur).unlink()

    def test_acl_manager_full_access(self):
        """AC #6 : Le responsable a un accès complet (CRUD) sur les attributs."""
        for model_name in self.ATTRIBUTE_MODELS:
            with self.subTest(model=model_name):
                Model = self.env[model_name].with_user(self.user_responsable)

                # Création
                record = Model.create({'name': 'Attribut Manager'})
                self.assertTrue(record.id)

                # Lecture
                Model.search([])

                # Modification
                record.write({'name': 'Attribut Modifié'})
                self.assertEqual(record.name, 'Attribut Modifié')

                # Suppression
                record.unlink()

    def test_no_ou_filtering(self):
        """AC #7 : Les attributs sont visibles par tous, sans filtrage Operating Unit."""
        for model_name in self.ATTRIBUTE_MODELS:
            with self.subTest(model=model_name):
                # Créer un attribut en admin
                record = self.env[model_name].create({'name': 'Attribut Global'})

                # Le vendeur (OU A) voit l'attribut
                visible_vendeur = self.env[model_name].with_user(self.user_vendeur).search(
                    [('id', '=', record.id)]
                )
                self.assertTrue(visible_vendeur, "Le vendeur doit voir l'attribut (pas de filtrage OU)")

                # Le responsable (OU A) voit l'attribut
                visible_responsable = self.env[model_name].with_user(self.user_responsable).search(
                    [('id', '=', record.id)]
                )
                self.assertTrue(visible_responsable, "Le responsable doit voir l'attribut")

    def test_color_field_default(self):
        """AC #3 : Le champ color a une valeur par défaut entre 1 et 11."""
        for model_name in self.ATTRIBUTE_MODELS:
            with self.subTest(model=model_name):
                record = self.env[model_name].create({'name': 'Test Couleur'})
                self.assertGreaterEqual(record.color, 1,
                                        "La couleur doit être >= 1")
                self.assertLessEqual(record.color, 11,
                                     "La couleur doit être <= 11")

    def test_menu_config_attributs_invisible_vendeur(self):
        """AC #2 : Les menus Configuration > Attributs ne sont pas visibles pour le vendeur."""
        menu_attributs = self.env.ref('optical.menu_optical_config_attributs')
        visible = self.env['ir.ui.menu'].with_user(self.user_vendeur).search(
            [('id', '=', menu_attributs.id)]
        )
        self.assertFalse(visible, "Le vendeur ne doit pas voir le menu Attributs")

        # Vérifier aussi les 5 sous-menus enfants
        sub_menu_refs = [
            'optical.menu_optical_config_attr_treatments',
            'optical.menu_optical_config_attr_tints',
            'optical.menu_optical_config_attr_materials',
            'optical.menu_optical_config_attr_colors',
            'optical.menu_optical_config_attr_usages',
        ]
        for ref in sub_menu_refs:
            with self.subTest(menu=ref):
                menu = self.env.ref(ref)
                visible = self.env['ir.ui.menu'].with_user(self.user_vendeur).search(
                    [('id', '=', menu.id)]
                )
                self.assertFalse(visible, f"Le vendeur ne doit pas voir le menu {ref}")
