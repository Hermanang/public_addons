# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from psycopg2 import IntegrityError

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestOpticalAttributes(OpticalTestCommon):
    """Tests Story 4.1 — Modèles attributs optiques et configuration.

    Story 19-1 (2026-07-23) : ajout du modèle optical.lens.thickness au sein
    de la famille des attributs — reprend l'ensemble des tests génériques
    via ATTRIBUTE_MODELS + 2 tests dédiés (unicité SQL, cycle manager).

    Story 19-3 (2026-07-23) : ajout du champ Selection `treatment_type` sur
    optical.lens.treatment — 3 tests dédiés en fin de classe (définition
    du champ, filtrage par domain base/complement/False, ACL vendeur R
    et manager RW).
    """

    ATTRIBUTE_MODELS = [
        'optical.lens.treatment',
        'optical.lens.tint',
        'optical.lens.thickness',
        'optical.frame.material',
        'optical.frame.color',
        'optical.frame.usage',
    ]

    def test_create_all_attributes(self):
        """AC #1, #3 : Création d'un attribut dans chacun des 6 modèles."""
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

        # Vérifier aussi les 7 sous-menus enfants (Story 19-1 : épaisseurs, Story 19-2 : indices)
        sub_menu_refs = [
            'optical.menu_optical_config_attr_treatments',
            'optical.menu_optical_config_attr_indices',
            'optical.menu_optical_config_attr_tints',
            'optical.menu_optical_config_attr_thicknesses',
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

    # ------------------------------------------------------------------
    # Story 19-1 — Tests dédiés `optical.lens.thickness`
    # ------------------------------------------------------------------

    def test_thickness_name_uniqueness(self):
        """Story 19-1 AC-1.2 : contrainte SQL unique sur name."""
        Model = self.env['optical.lens.thickness']
        Model.create({'name': 'Aminci'})
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            Model.create({'name': 'Aminci'})

    def test_thickness_manager_can_deactivate(self):
        """Story 19-1 AC-4.3 : le responsable peut créer puis désactiver."""
        Model = self.env['optical.lens.thickness'].with_user(self.user_responsable)
        record = Model.create({'name': 'Super Aminci', 'sequence': 30})
        self.assertTrue(record.active)
        record.write({'active': False})
        self.assertFalse(record.active)
        # Recherche par défaut filtre active=True → l'enregistrement disparaît
        visible = Model.search([('name', '=', 'Super Aminci')])
        self.assertFalse(visible)

    def test_thickness_acl_non_optical_user_denied(self):
        """Story 19-1 AC-3.3 : utilisateur sans groupe optique → AccessError en lecture."""
        record = self.env['optical.lens.thickness'].create({'name': 'Test Refus Lecture'})
        with self.assertRaises(AccessError):
            record.with_user(self.user_sans_groupe).read(['name'])

    # ------------------------------------------------------------------
    # Story 19-3 — Tests dédiés `treatment_type` sur `optical.lens.treatment`
    # ------------------------------------------------------------------

    def test_treatment_type_field_definition(self):
        """Story 19-3 AC-1.1 : le champ treatment_type est Selection avec 2 valeurs, optionnel."""
        field = self.env['optical.lens.treatment']._fields.get('treatment_type')
        self.assertIsNotNone(field, "Le champ treatment_type doit exister")
        self.assertEqual(field.type, 'selection')
        # Odoo 18 : selection peut être callable — utiliser _description_selection
        selection = field._description_selection(self.env)
        keys = [k for k, _ in selection]
        self.assertIn('base', keys)
        self.assertIn('complement', keys)
        self.assertFalse(field.required, "treatment_type doit être required=False (cadrage Q24)")

    def test_treatment_type_domain_filtering(self):
        """Story 19-3 AC-3 : filtrage par domain base/complement/False fonctionne."""
        Model = self.env['optical.lens.treatment']
        t_base = Model.create({'name': 'Photochromique Test', 'treatment_type': 'base'})
        t_complement = Model.create({'name': 'Antireflet Test S19-3', 'treatment_type': 'complement'})
        t_none = Model.create({'name': 'Traitement Non Catégorisé Test', 'treatment_type': False})
        # AC-3.1 — base
        result_base = Model.search([('treatment_type', '=', 'base')])
        self.assertIn(t_base, result_base)
        self.assertNotIn(t_complement, result_base)
        self.assertNotIn(t_none, result_base)
        # AC-3.2 — complement
        result_comp = Model.search([('treatment_type', '=', 'complement')])
        self.assertIn(t_complement, result_comp)
        self.assertNotIn(t_base, result_comp)
        self.assertNotIn(t_none, result_comp)
        # AC-3.3 — non catégorisé (t_none doit remonter — d'autres fixtures peuvent
        # aussi être non-catégorisées, on n'assert que la présence de t_none).
        # En revanche t_base et t_complement (treatment_type != False) doivent
        # être exclus — garde-fou contre un bug type « domaine False = tout ».
        result_none = Model.search([('treatment_type', '=', False)])
        self.assertIn(t_none, result_none)
        self.assertNotIn(t_base, result_none)
        self.assertNotIn(t_complement, result_none)

    def test_treatment_type_vendor_readonly(self):
        """Story 19-3 AC-1.3 + AC-1.4 : le manager crée+modifie, le vendeur lit seulement."""
        # AC-1.3 : le manager crée avec treatment_type puis bascule complement → base
        Model = self.env['optical.lens.treatment'].with_user(self.user_responsable)
        record = Model.create({
            'name': 'Traitement Test Vendeur',
            'treatment_type': 'complement',
        })
        self.assertEqual(record.treatment_type, 'complement')
        record.write({'treatment_type': 'base'})
        self.assertEqual(record.treatment_type, 'base')
        # AC-1.4 : lecture vendeur autorisée (ACL user = read only)
        data = record.with_user(self.user_vendeur).read(['treatment_type'])
        self.assertEqual(data[0]['treatment_type'], 'base')
        # AC-1.4 : écriture vendeur refusée (ACL générique — pas de règle par champ)
        with self.assertRaises(AccessError):
            record.with_user(self.user_vendeur).write({'treatment_type': 'complement'})
