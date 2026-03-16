# -*- coding: utf-8 -*-
"""Tests Stories 11.1 & 11.2 : Migration attributs, prescriptions, partenaires.

Ces tests verifient que les modeles et données sont corrects apres migration.
La migration elle-meme s'execute a l'installation/upgrade du module — les tests
valident l'etat final, pas le processus de migration.
"""
from psycopg2 import sql

from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestMigrationAttributes(OpticalTestCommon):
    """Tests AC#1 : les modeles attributs sont accessibles apres migration."""

    def test_attribute_models_accessible(self):
        """Les 5 modeles attributs sont accessibles via l'ORM."""
        models = [
            'optical.frame.material',
            'optical.frame.color',
            'optical.frame.usage',
            'optical.lens.treatment',
            'optical.lens.tint',
        ]
        for model_name in models:
            with self.subTest(model=model_name):
                Model = self.env[model_name]
                # Le modele est accessible et queryable
                self.assertTrue(Model._name, model_name)
                # On peut faire un search sans erreur
                Model.search([], limit=1)

    def test_attribute_models_crud(self):
        """CRUD operations fonctionnent sur les modeles attributs."""
        record = self.env['optical.frame.material'].create({
            'name': 'Test Migration Material',
        })
        self.assertTrue(record.id)
        self.assertEqual(record.name, 'Test Migration Material')

        # Read
        record.read(['name'])

        # Write
        record.write({'name': 'Test Migration Material Updated'})
        self.assertEqual(record.name, 'Test Migration Material Updated')

        # Search
        found = self.env['optical.frame.material'].search([
            ('name', '=', 'Test Migration Material Updated'),
        ])
        self.assertEqual(len(found), 1)

    def test_m2m_relations_functional(self):
        """Les relations Many2many entre product.template et attributs fonctionnent."""
        material = self.env['optical.frame.material'].create({
            'name': 'Test M2M Material',
        })
        color = self.env['optical.frame.color'].create({
            'name': 'Test M2M Color',
        })

        product = self.env['product.template'].create({
            'name': 'Test M2M Product',
            'optical_type': 'frame',
            'frame_material_ids': [(4, material.id)],
            'frame_color_ids': [(4, color.id)],
        })

        self.assertIn(material, product.frame_material_ids)
        self.assertIn(color, product.frame_color_ids)

    def test_ir_model_data_namespace(self):
        """Aucune reference ir_model_data avec module = 'otn_optical' ne subsiste."""
        otn_refs = self.env['ir.model.data'].search([
            ('module', '=', 'otn_optical'),
        ])
        self.assertFalse(
            otn_refs,
            "Des references ir_model_data avec module='otn_optical' subsistent : %s"
            % otn_refs.mapped('name'),
        )


@tagged('post_install', '-at_install')
class TestMigrationOpticalType(OpticalTestCommon):
    """Tests AC#2 : les valeurs optical_type sont correctes apres migration."""

    def test_optical_type_values_valid(self):
        """Toutes les valeurs optical_type en base sont des valeurs valides."""
        valid_values = {'frame', 'lens', 'contact_lens', 'accessory', 'service', False}
        self.env.cr.execute("""
            SELECT DISTINCT optical_type FROM product_template
            WHERE optical_type IS NOT NULL
        """)
        db_values = {row[0] for row in self.env.cr.fetchall()}
        invalid = db_values - valid_values
        self.assertFalse(
            invalid,
            "Valeurs optical_type invalides trouvées en base : %s" % invalid,
        )

    def test_no_old_optical_type_values(self):
        """Aucune ancienne valeur (frames, lenses, etc.) ne subsiste."""
        old_values = ('frames', 'lenses', 'contact_lenses', 'others')
        self.env.cr.execute("""
            SELECT COUNT(*) FROM product_template
            WHERE optical_type IN %s
        """, (old_values,))
        count = self.env.cr.fetchone()[0]
        self.assertEqual(
            count, 0,
            "Anciennes valeurs optical_product_type subsistent en base",
        )

    def test_optical_type_field_exists(self):
        """Le champ optical_type existe sur product.template (pas optical_product_type)."""
        self.assertIn(
            'optical_type',
            self.env['product.template']._fields,
            "Le champ optical_type n'existe pas sur product.template",
        )

    def test_product_classification_works(self):
        """Un produit peut etre classifie avec les nouvelles valeurs."""
        product = self.env['product.template'].create({
            'name': 'Test Classification',
            'optical_type': 'frame',
        })
        self.assertEqual(product.optical_type, 'frame')

        product.write({'optical_type': 'lens'})
        self.assertEqual(product.optical_type, 'lens')

        product.write({'optical_type': 'contact_lens'})
        self.assertEqual(product.optical_type, 'contact_lens')

        product.write({'optical_type': 'accessory'})
        self.assertEqual(product.optical_type, 'accessory')


@tagged('post_install', '-at_install')
class TestMigrationLensDesign(OpticalTestCommon):
    """Tests AC#3 : lens_design est fonctionnel apres migration."""

    def test_lens_design_field_functional(self):
        """Le champ lens_design fonctionne correctement."""
        product = self.env['product.template'].create({
            'name': 'Test Lens Design',
            'optical_type': 'lens',
            'lens_design': 'progressive',
        })
        self.assertEqual(product.lens_design, 'progressive')

    def test_no_orphan_lens_type_table(self):
        """La table product_lens_type n'existe plus."""
        self.env.cr.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'product_lens_type' AND table_schema = 'public'
            )
        """)
        exists = self.env.cr.fetchone()[0]
        self.assertFalse(
            exists,
            "La table orpheline product_lens_type existe encore en base",
        )


@tagged('post_install', '-at_install')
class TestMigrationIdempotence(OpticalTestCommon):
    """Tests AC#5 : la migration est idempotente."""

    def test_migration_functions_idempotent(self):
        """Les fonctions de migration s'executent sans erreur sur une base propre."""
        from odoo.addons.optical.migrations.migrate_otn_optical import (
            migrate_attribute_tables,
            migrate_optical_type,
            migrate_prescription_measures,
            migrate_partner_flags,
            migrate_woo_attribute_mappings,
            migrate_lens_type_to_design,
            cleanup_orphan_tables,
        )
        cr = self.env.cr

        # Executer les fonctions individuelles sur une base sans données otn_optical
        # Aucune erreur ne doit se produire (gardes d'idempotence)
        # Note : on n'appelle pas pre_migrate_from_otn() car update_module_names
        # echoue quand le module optical est deja installe (contrainte unique)
        migrate_attribute_tables(cr)
        migrate_optical_type(cr)
        migrate_prescription_measures(cr)
        migrate_partner_flags(cr)
        migrate_woo_attribute_mappings(cr)
        migrate_lens_type_to_design(cr)
        cleanup_orphan_tables(cr)

        # Verifier que les modeles sont toujours accessibles
        self.env['optical.frame.material'].search([], limit=1)
        self.env['optical.frame.color'].search([], limit=1)
        self.env['optical.lens.treatment'].search([], limit=1)

    def test_pre_init_hook_idempotent(self):
        """Le pre_init_hook s'execute sans erreur meme sans données otn_optical."""
        from odoo.addons.optical.hooks import pre_init_hook
        # Ne doit pas lever d'exception
        pre_init_hook(self.env)

    def test_module_upgrade_no_error(self):
        """Le module peut etre mis a jour sans erreur (simulation)."""
        # Verifier que tous les modeles sont accessibles apres un 'upgrade'
        # En test, le module est deja installe — verifier l'etat final
        models_to_check = [
            'optical.frame.material',
            'optical.frame.color',
            'optical.frame.usage',
            'optical.lens.treatment',
            'optical.lens.tint',
            'product.template',
        ]
        for model_name in models_to_check:
            with self.subTest(model=model_name):
                self.assertIn(model_name, self.env)
                self.env[model_name].search([], limit=1)


# ===========================================================================
# Story 11.2 : Migration prescriptions et partenaires
# ===========================================================================

@tagged('post_install', '-at_install')
class TestMigrationPrescriptionMeasures(OpticalTestCommon):
    """Tests Story 11.2 AC#1 : mesures prescriptions en Float/Integer."""

    def test_prescription_field_types_float(self):
        """Les champs mesures sont de type Float."""
        fields = self.env['optical.prescription']._fields
        float_field_names = [
            'od_sphere', 'od_cylinder', 'od_addition', 'od_prism',
            'og_sphere', 'og_cylinder', 'og_addition', 'og_prism',
            'od_pd', 'og_pd', 'pd_total',
        ]
        for field_name in float_field_names:
            with self.subTest(field=field_name):
                self.assertIn(field_name, fields)
                self.assertEqual(
                    fields[field_name].type, 'float',
                    "%s devrait etre de type float" % field_name,
                )

    def test_prescription_field_types_integer(self):
        """Les champs axis sont de type Integer."""
        fields = self.env['optical.prescription']._fields
        for field_name in ('od_axis', 'og_axis'):
            with self.subTest(field=field_name):
                self.assertIn(field_name, fields)
                self.assertEqual(
                    fields[field_name].type, 'integer',
                    "%s devrait etre de type integer" % field_name,
                )

    def test_prescription_pd_columns_exist(self):
        """Les colonnes PD (od_pd, og_pd, pd_total) existent en base."""
        for col in ('od_pd', 'og_pd', 'pd_total'):
            with self.subTest(column=col):
                self.env.cr.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'optical_prescription'
                          AND column_name = %s
                    )
                """, (col,))
                self.assertTrue(
                    self.env.cr.fetchone()[0],
                    "Colonne %s introuvable dans optical_prescription" % col,
                )

    def test_prism_base_selection_values(self):
        """Les valeurs de base prisme sont up/down/in/out."""
        fields = self.env['optical.prescription']._fields
        for field_name in ('od_prism_base', 'og_prism_base'):
            with self.subTest(field=field_name):
                selection_keys = [k for k, _ in fields[field_name].selection]
                self.assertEqual(
                    sorted(selection_keys),
                    ['down', 'in', 'out', 'up'],
                )

    def test_no_old_prism_base_values(self):
        """Aucune ancienne valeur prism_base (inferior, superior, etc.) en base."""
        old_values = ('inferior', 'superior', 'nasal', 'temporal')
        self.env.cr.execute("""
            SELECT COUNT(*) FROM optical_prescription
            WHERE od_prism_base IN %s OR og_prism_base IN %s
        """, (old_values, old_values))
        count = self.env.cr.fetchone()[0]
        self.assertEqual(
            count, 0,
            "Anciennes valeurs prism_base subsistent en base",
        )

    def test_prescription_sequence_preserved(self):
        """Les sequences prescriptions sont fonctionnelles apres migration."""
        prescription = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
        })
        # La sequence du module optical utilise le prefixe ORD/
        # En production (ancien module otn_optical), les sequences PH-xxxx
        # sont preservées car la migration ne touche pas ir.sequence
        self.assertTrue(
            prescription.name and '/' in prescription.name,
            "Sequence prescription invalide: %s" % prescription.name,
        )

    def test_prescription_measures_crud(self):
        """CRUD sur les mesures numeriques fonctionne correctement."""
        prescription = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
            'od_sphere': 2.50,
            'od_cylinder': -1.25,
            'od_axis': 90,
            'od_addition': 1.50,
            'od_pd': 32.0,
        })
        self.assertEqual(prescription.od_sphere, 2.50)
        self.assertEqual(prescription.od_cylinder, -1.25)
        self.assertEqual(prescription.od_axis, 90)
        self.assertEqual(prescription.od_addition, 1.50)
        self.assertEqual(prescription.od_pd, 32.0)


@tagged('post_install', '-at_install')
class TestMigrationPartnerFlags(OpticalTestCommon):
    """Tests Story 11.2 AC#2 : flags partenaires."""

    def test_partner_boolean_fields_exist(self):
        """Les champs is_patient et is_prescriber existent sur res.partner."""
        fields = self.env['res.partner']._fields
        self.assertIn('is_patient', fields)
        self.assertIn('is_prescriber', fields)
        self.assertEqual(fields['is_patient'].type, 'boolean')
        self.assertEqual(fields['is_prescriber'].type, 'boolean')

    def test_prescriber_flag_functional(self):
        """Le flag is_prescriber fonctionne en creation et recherche."""
        prescriber = self.env['res.partner'].create({
            'name': 'Test Prescriber Migration',
            'is_prescriber': True,
        })
        self.assertTrue(prescriber.is_prescriber)

        found = self.env['res.partner'].search([
            ('id', '=', prescriber.id),
            ('is_prescriber', '=', True),
        ])
        self.assertEqual(len(found), 1)

    def test_patient_flag_functional(self):
        """Le flag is_patient fonctionne en creation et recherche."""
        patient = self.env['res.partner'].create({
            'name': 'Test Patient Migration',
            'is_patient': True,
        })
        self.assertTrue(patient.is_patient)

        found = self.env['res.partner'].search([
            ('id', '=', patient.id),
            ('is_patient', '=', True),
        ])
        self.assertEqual(len(found), 1)


@tagged('post_install', '-at_install')
class TestMigration112Idempotence(OpticalTestCommon):
    """Tests Story 11.2 AC#4 : idempotence des fonctions de migration."""

    def test_prescription_migration_idempotent(self):
        """migrate_prescription_measures s'execute sans erreur sur base propre."""
        from odoo.addons.optical.migrations.migrate_otn_optical import (
            migrate_prescription_measures,
        )
        # Executer sur une base sans données legacy — aucune erreur
        migrate_prescription_measures(self.env.cr)
        self.env['optical.prescription'].search([], limit=1)

    def test_partner_migration_idempotent(self):
        """migrate_partner_flags s'execute sans erreur sur base propre."""
        from odoo.addons.optical.migrations.migrate_otn_optical import (
            migrate_partner_flags,
        )
        migrate_partner_flags(self.env.cr)
        self.env['res.partner'].search([], limit=1)

    def test_full_112_migration_idempotent(self):
        """Les fonctions 11-2 combinées s'executent sans erreur."""
        from odoo.addons.optical.migrations.migrate_otn_optical import (
            migrate_prescription_measures,
            migrate_partner_flags,
        )
        cr = self.env.cr
        migrate_prescription_measures(cr)
        migrate_partner_flags(cr)
        # Modeles toujours accessibles
        self.env['optical.prescription'].search([], limit=1)
        self.env['res.partner'].search([], limit=1)



# ===========================================================================
# Story 11.2 : Tests de conversion effective des données legacy
# ===========================================================================

@tagged('post_install', '-at_install')
class TestMigrationDataConversion(OpticalTestCommon):
    """Tests Story 11.2 : conversion effective des données legacy."""

    def test_char_to_float_conversion(self):
        """Conversion Char → Float avec trim et NULLIF."""
        from odoo.addons.optical.migrations.migrate_otn_optical import (
            migrate_prescription_measures,
        )
        cr = self.env.cr
        prescription = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
        })
        pid = prescription.id
        # Simuler colonne Char legacy
        cr.execute(
            "ALTER TABLE optical_prescription "
            "ALTER COLUMN od_sphere TYPE varchar USING od_sphere::text"
        )
        cr.execute(
            "UPDATE optical_prescription SET od_sphere = %s WHERE id = %s",
            ('  -1.75  ', pid),
        )
        migrate_prescription_measures(cr)
        cr.execute(
            "SELECT od_sphere FROM optical_prescription WHERE id = %s", (pid,)
        )
        self.assertAlmostEqual(cr.fetchone()[0], -1.75)

    def test_char_to_integer_conversion(self):
        """Conversion Char → Integer avec trim et NULLIF."""
        from odoo.addons.optical.migrations.migrate_otn_optical import (
            migrate_prescription_measures,
        )
        cr = self.env.cr
        prescription = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
        })
        pid = prescription.id
        cr.execute(
            "ALTER TABLE optical_prescription "
            "ALTER COLUMN od_axis TYPE varchar USING od_axis::text"
        )
        cr.execute(
            "UPDATE optical_prescription SET od_axis = %s WHERE id = %s",
            (' 45 ', pid),
        )
        migrate_prescription_measures(cr)
        cr.execute(
            "SELECT od_axis FROM optical_prescription WHERE id = %s", (pid,)
        )
        self.assertEqual(cr.fetchone()[0], 45)

    def test_empty_string_becomes_null(self):
        """Les valeurs vides sont converties en NULL."""
        from odoo.addons.optical.migrations.migrate_otn_optical import (
            migrate_prescription_measures,
        )
        cr = self.env.cr
        prescription = self.env['optical.prescription'].create({
            'patient_id': self.patient.id,
            'prescriber_id': self.prescriber.id,
        })
        pid = prescription.id
        cr.execute(
            "ALTER TABLE optical_prescription "
            "ALTER COLUMN og_sphere TYPE varchar USING og_sphere::text"
        )
        cr.execute(
            "UPDATE optical_prescription SET og_sphere = %s WHERE id = %s",
            ('  ', pid),
        )
        migrate_prescription_measures(cr)
        cr.execute(
            "SELECT og_sphere FROM optical_prescription WHERE id = %s", (pid,)
        )
        self.assertIsNone(cr.fetchone()[0])

    def test_is_clinical_to_is_prescriber(self):
        """is_clinical = true → is_prescriber = true."""
        from odoo.addons.optical.migrations.migrate_otn_optical import (
            migrate_partner_flags,
        )
        cr = self.env.cr
        partner = self.env['res.partner'].create({
            'name': 'Test Clinical Partner',
        })
        # Ajouter la colonne is_clinical si absente (simuler ancien module)
        cr.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'res_partner' AND column_name = 'is_clinical'
            )
        """)
        if not cr.fetchone()[0]:
            cr.execute(
                "ALTER TABLE res_partner "
                "ADD COLUMN is_clinical boolean DEFAULT false"
            )
        cr.execute(
            "UPDATE res_partner SET is_clinical = true WHERE id = %s",
            (partner.id,),
        )
        migrate_partner_flags(cr)
        cr.execute(
            "SELECT is_prescriber FROM res_partner WHERE id = %s",
            (partner.id,),
        )
        self.assertTrue(cr.fetchone()[0])


# ===========================================================================
# Story 11.3 : Migration relations partenaires → polices
# ===========================================================================

@tagged('post_install', '-at_install')
class TestMigration113Policies(OpticalTestCommon):
    """Tests Story 11.3 : conversion relations en polices et nettoyage."""

    def test_policy_model_accessible(self):
        """AC#1: Le modele optical.policy est accessible et fonctionnel."""
        Model = self.env['optical.policy']
        self.assertEqual(Model._name, 'optical.policy')
        Model.search([], limit=1)

    def test_policy_crud(self):
        """AC#1: CRUD sur optical.policy fonctionne."""
        policy = self.env['optical.policy'].create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'coverage_rate': 80.0,
            'date_start': '2024-01-01',
            'date_end': '2025-12-31',
        })
        self.assertTrue(policy.id)
        self.assertEqual(policy.state, 'active')
        self.assertEqual(policy.coverage_rate, 80.0)

    def test_is_insurer_flag(self):
        """AC#1: Le flag is_insurer fonctionne sur res.partner."""
        insurer = self.env['res.partner'].create({
            'name': 'Test Assureur 11-3',
            'is_insurer': True,
        })
        self.assertTrue(insurer.is_insurer)
        found = self.env['res.partner'].search([
            ('id', '=', insurer.id),
            ('is_insurer', '=', True),
        ])
        self.assertEqual(len(found), 1)

    def test_mark_insurers_from_relations_with_simulated_data(self):
        """AC#1: Marquage is_insurer depuis relations simulées."""
        from odoo.addons.optical.migrations.migrate_otn_optical import (
            mark_insurers_from_relations,
        )
        cr = self.env.cr

        # Creer les tables legacy si absentes
        cr.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'res_partner_relation_type'
                  AND table_schema = 'public'
            )
        """)
        has_type_table = cr.fetchone()[0]

        if not has_type_table:
            cr.execute("""
                CREATE TABLE res_partner_relation_type (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(128),
                    name_inverse VARCHAR(128)
                )
            """)

        cr.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'res_partner_relation'
                  AND table_schema = 'public'
            )
        """)
        has_relation_table = cr.fetchone()[0]

        if not has_relation_table:
            cr.execute("""
                CREATE TABLE res_partner_relation (
                    id SERIAL PRIMARY KEY,
                    type_id INTEGER,
                    left_partner_id INTEGER,
                    right_partner_id INTEGER
                )
            """)

        # Inserer un type de relation "A souscris chez"
        cr.execute("""
            INSERT INTO res_partner_relation_type (name, name_inverse)
            VALUES ('A souscris chez', 'Est assureur de')
            RETURNING id
        """)
        type_id = cr.fetchone()[0]

        # Creer des patients et assureurs de test
        patient1 = self.env['res.partner'].create({
            'name': 'Patient Relation Test 1',
            'is_patient': True,
        })
        assureur = self.env['res.partner'].create({
            'name': 'Assureur Relation Test',
        })

        # Inserer des relations
        cr.execute("""
            INSERT INTO res_partner_relation (type_id, left_partner_id, right_partner_id)
            VALUES (%s, %s, %s)
        """, (type_id, patient1.id, assureur.id))

        # Executer le marquage
        mark_insurers_from_relations(cr)

        # Verifier que l'assureur est marque is_insurer
        assureur.invalidate_recordset()
        cr.execute(
            "SELECT is_insurer FROM res_partner WHERE id = %s",
            (assureur.id,),
        )
        self.assertTrue(cr.fetchone()[0],
                        "L'assureur aurait du etre marque is_insurer=true")

        # Nettoyage
        cr.execute("DELETE FROM res_partner_relation WHERE type_id = %s", (type_id,))
        cr.execute("DELETE FROM res_partner_relation_type WHERE id = %s", (type_id,))
        if not has_relation_table:
            cr.execute("DROP TABLE IF EXISTS res_partner_relation CASCADE")
        if not has_type_table:
            cr.execute("DROP TABLE IF EXISTS res_partner_relation_type CASCADE")

    def test_idempotence_no_relations(self):
        """AC#5: mark_insurers_from_relations sans données legacy."""
        from odoo.addons.optical.migrations.migrate_otn_optical import (
            mark_insurers_from_relations,
        )
        # La fonction ne doit pas lever d'erreur meme sans tables legacy
        mark_insurers_from_relations(self.env.cr)

    def test_idempotence_double_run(self):
        """AC#5: Executer 2 fois le marquage ne cause pas d'erreur."""
        from odoo.addons.optical.migrations.migrate_otn_optical import (
            mark_insurers_from_relations,
        )
        cr = self.env.cr

        # Creer les tables legacy
        cr.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'res_partner_relation_type'
                  AND table_schema = 'public'
            )
        """)
        has_type_table = cr.fetchone()[0]

        if not has_type_table:
            cr.execute("""
                CREATE TABLE res_partner_relation_type (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(128),
                    name_inverse VARCHAR(128)
                )
            """)

        cr.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'res_partner_relation'
                  AND table_schema = 'public'
            )
        """)
        has_relation_table = cr.fetchone()[0]

        if not has_relation_table:
            cr.execute("""
                CREATE TABLE res_partner_relation (
                    id SERIAL PRIMARY KEY,
                    type_id INTEGER,
                    left_partner_id INTEGER,
                    right_partner_id INTEGER
                )
            """)

        cr.execute("""
            INSERT INTO res_partner_relation_type (name, name_inverse)
            VALUES ('A souscris chez', 'Est assureur de')
            RETURNING id
        """)
        type_id = cr.fetchone()[0]

        assureur = self.env['res.partner'].create({
            'name': 'Assureur Idempotence',
        })

        cr.execute("""
            INSERT INTO res_partner_relation (type_id, left_partner_id, right_partner_id)
            VALUES (%s, %s, %s)
        """, (type_id, self.patient.id, assureur.id))

        # Premiere execution
        mark_insurers_from_relations(cr)
        assureur.invalidate_recordset()
        cr.execute(
            "SELECT is_insurer FROM res_partner WHERE id = %s",
            (assureur.id,),
        )
        self.assertTrue(cr.fetchone()[0])

        # Deuxieme execution (idempotence)
        mark_insurers_from_relations(cr)

        # Nettoyage
        cr.execute("DELETE FROM res_partner_relation WHERE type_id = %s", (type_id,))
        cr.execute("DELETE FROM res_partner_relation_type WHERE id = %s", (type_id,))
        if not has_relation_table:
            cr.execute("DROP TABLE IF EXISTS res_partner_relation CASCADE")
        if not has_type_table:
            cr.execute("DROP TABLE IF EXISTS res_partner_relation_type CASCADE")


@tagged('post_install', '-at_install')
class TestMigration113Cleanup(OpticalTestCommon):
    """Tests Story 11.3 AC#2, AC#3: nettoyage colonnes et tables."""

    def test_cleanup_account_move_columns_empty(self):
        """AC#2: Colonnes vides sont supprimées."""
        from odoo.addons.optical.migrations.migrate_otn_optical import (
            cleanup_account_move_columns,
        )
        cr = self.env.cr

        # Ajouter une colonne de test
        test_col = 'optical_subscriber_id'
        if not self._column_exists(cr, 'account_move', test_col):
            cr.execute(sql.SQL(
                "ALTER TABLE account_move ADD COLUMN {} integer"
            ).format(sql.Identifier(test_col)))

        cleanup_account_move_columns(cr)

        # Verifier que la colonne a ete supprimee (etait vide)
        self.assertFalse(
            self._column_exists(cr, 'account_move', test_col),
            "La colonne vide %s aurait du etre supprimee" % test_col,
        )

    def test_cleanup_account_move_columns_non_empty(self):
        """AC#2: Colonnes avec données sont preservées."""
        from odoo.addons.optical.migrations.migrate_otn_optical import (
            cleanup_account_move_columns,
        )
        cr = self.env.cr

        test_col = 'optical_insurance_id'
        if not self._column_exists(cr, 'account_move', test_col):
            cr.execute(sql.SQL(
                "ALTER TABLE account_move ADD COLUMN {} integer"
            ).format(sql.Identifier(test_col)))

        # Creer un account_move de test pour garantir une ligne
        move = self.env['account.move'].create({
            'move_type': 'entry',
        })

        # Inserer une valeur pour que la colonne ne soit pas vide
        cr.execute(
            "UPDATE account_move SET optical_insurance_id = 1 WHERE id = %s",
            (move.id,),
        )
        self.assertEqual(cr.rowcount, 1, "L'UPDATE devrait toucher 1 ligne")

        cleanup_account_move_columns(cr)

        # Verifier que la colonne est preservee (non-vide)
        self.assertTrue(
            self._column_exists(cr, 'account_move', test_col),
            "La colonne non-vide %s aurait du etre preservee" % test_col,
        )

        # Nettoyage
        if self._column_exists(cr, 'account_move', test_col):
            cr.execute(sql.SQL(
                "ALTER TABLE account_move DROP COLUMN IF EXISTS {}"
            ).format(sql.Identifier(test_col)))

    def test_cleanup_empty_legacy_tables(self):
        """AC#3: Tables vides sont supprimées."""
        from odoo.addons.optical.migrations.migrate_otn_optical import (
            cleanup_empty_legacy_tables,
        )
        cr = self.env.cr

        # Creer une table de test vide
        cr.execute("""
            CREATE TABLE IF NOT EXISTS optical_insurance_policy (
                id SERIAL PRIMARY KEY,
                name VARCHAR(128)
            )
        """)
        # S'assurer qu'elle est vide
        cr.execute("DELETE FROM optical_insurance_policy")

        cleanup_empty_legacy_tables(cr)

        # Verifier que la table a ete supprimee
        cr.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'optical_insurance_policy'
                  AND table_schema = 'public'
            )
        """)
        self.assertFalse(cr.fetchone()[0],
                         "La table vide optical_insurance_policy aurait du etre supprimee")

        # Verifier que ir_model_data et ir_model ont ete nettoyes
        cr.execute("""
            SELECT COUNT(*) FROM ir_model_data
            WHERE model = 'optical.insurance.policy'
        """)
        self.assertEqual(cr.fetchone()[0], 0,
                         "ir_model_data pour optical.insurance.policy aurait du etre nettoye")
        cr.execute("""
            SELECT COUNT(*) FROM ir_model
            WHERE model = 'optical.insurance.policy'
        """)
        self.assertEqual(cr.fetchone()[0], 0,
                         "ir_model pour optical.insurance.policy aurait du etre nettoye")

    def test_cleanup_non_empty_legacy_table(self):
        """AC#3: Tables non-vides sont preservées."""
        from odoo.addons.optical.migrations.migrate_otn_optical import (
            cleanup_empty_legacy_tables,
        )
        cr = self.env.cr

        cr.execute("""
            CREATE TABLE IF NOT EXISTS optical_insurance_policy (
                id SERIAL PRIMARY KEY,
                name VARCHAR(128)
            )
        """)
        cr.execute("""
            INSERT INTO optical_insurance_policy (name) VALUES ('test')
        """)

        cleanup_empty_legacy_tables(cr)

        cr.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'optical_insurance_policy'
                  AND table_schema = 'public'
            )
        """)
        self.assertTrue(cr.fetchone()[0],
                        "La table non-vide aurait du etre preservee")

        # Nettoyage
        cr.execute("DROP TABLE IF EXISTS optical_insurance_policy CASCADE")

    def test_cleanup_functions_idempotent(self):
        """AC#5: Les fonctions de nettoyage s'executent sans erreur sur base propre."""
        from odoo.addons.optical.migrations.migrate_otn_optical import (
            cleanup_account_move_columns,
            cleanup_empty_legacy_tables,
        )
        cr = self.env.cr
        # Sans tables legacy, ne doit pas lever d'erreur
        cleanup_account_move_columns(cr)
        cleanup_empty_legacy_tables(cr)

    @staticmethod
    def _column_exists(cr, table, column):
        """Helper : verifie si une colonne existe dans une table."""
        cr.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = %s AND column_name = %s
            )
        """, (table, column))
        return cr.fetchone()[0]


@tagged('post_install', '-at_install')
class TestMigration113Independence(OpticalTestCommon):
    """Tests Story 11.3 AC#4: independence vis-a-vis de partner_multi_relation."""

    def test_optical_no_dependency_partner_multi_relation(self):
        """AC#4: Le module optical ne depend pas de partner_multi_relation."""
        manifest = self.env['ir.module.module'].search([
            ('name', '=', 'optical'),
        ])
        self.assertTrue(manifest)
        deps = self.env['ir.module.module.dependency'].search([
            ('module_id', '=', manifest.id),
        ])
        dep_names = deps.mapped('name')
        self.assertNotIn('partner_multi_relation', dep_names,
                         "Le module optical ne doit pas dependre de partner_multi_relation")
