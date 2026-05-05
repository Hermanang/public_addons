# -*- coding: utf-8 -*-
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestBridgeDynamicColumns(TransactionCase):
    """Tests Story 13-2 : Bridge optical_report_columns — colonnes bordereau."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Column = cls.env['report.dynamic.column']

        # Créer un utilisateur responsable optique pour l'approbation PEC
        # Ajouter le groupe access_all OU pour contourner les record rules OU
        groups = [
            cls.env.ref('optical.group_optical_manager').id,
            cls.env.ref('base.group_user').id,
            cls.env.ref('sales_team.group_sale_salesman').id,
        ]
        group_all_ou = cls.env.ref(
            'operating_unit_access_all.group_all_operating_unit',
            raise_if_not_found=False,
        )
        if group_all_ou:
            groups.append(group_all_ou.id)
        cls.user_manager = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Responsable Bridge Test',
            'login': 'responsable_bridge_test',
            'email': 'resp_bridge@test.com',
            'groups_id': [Command.set(groups)],
        })

        # Créer un patient
        cls.patient = cls.env['res.partner'].create({
            'name': 'Patient Test Bridge',
            'is_patient': True,
        })

        # Créer un assureur IPM
        cls.insurer_ipm = cls.env['res.partner'].create({
            'name': 'IPM Test Bridge',
            'is_insurer': True,
            'insurer_type': 'ipm',
        })

        # Créer un assureur assurance
        cls.insurer_insurance = cls.env['res.partner'].create({
            'name': 'Assurance Test Bridge',
            'is_insurer': True,
            'insurer_type': 'insurance',
        })

        # Créer un souscripteur
        cls.subscriber = cls.env['res.partner'].create({
            'name': 'Entreprise Souscripteur Bridge',
            'is_company': True,
        })

        # Plan de couverture 100%
        cls.plan = cls.env['optical.insurer.plan'].create({
            'name': 'Plan Bridge Test',
            'insurer_id': cls.insurer_ipm.id,
            'default_coverage_rate': 100.0,
            'billing_mode': 'third_party',
        })
        cls.env['optical.coverage.rule'].create({
            'plan_id': cls.plan.id,
            'product_category': 'frame',
            'coverage_rate': 100.0,
        })
        cls.env['optical.coverage.rule'].create({
            'plan_id': cls.plan.id,
            'product_category': 'lens',
            'coverage_rate': 100.0,
        })

        # Police
        cls.policy = cls.env['optical.policy'].create({
            'patient_id': cls.patient.id,
            'insurer_id': cls.insurer_ipm.id,
            'coverage_rate': 100.0,
            'plan_id': cls.plan.id,
            'subscriber_id': cls.subscriber.id,
            'beneficiary_relationship': 'holder',
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',
        })

        # Produits
        cls.product_monture = cls.env['product.product'].create({
            'name': 'Monture Bridge Test',
            'type': 'consu',
            'list_price': 50000.0,
            'taxes_id': [],
        })
        cls.product_monture.product_tmpl_id.optical_type = 'frame'

        cls.product_verre = cls.env['product.product'].create({
            'name': 'Verre Bridge Test',
            'type': 'consu',
            'list_price': 30000.0,
            'taxes_id': [],
        })
        cls.product_verre.product_tmpl_id.optical_type = 'lens'

        # Créer un sale order et une PEC approuvée → factures
        cls.sale_order = cls.env['sale.order'].create({
            'partner_id': cls.patient.id,
            'policy_id': cls.policy.id,
            'order_line': [
                Command.create({
                    'product_id': cls.product_monture.id,
                    'product_uom_qty': 1,
                    'price_unit': 50000.0,
                }),
                Command.create({
                    'product_id': cls.product_verre.id,
                    'product_uom_qty': 1,
                    'price_unit': 30000.0,
                }),
            ],
        })
        cls.sale_order.action_create_pec()
        cls.sale_order.action_confirm()
        cls.pec = cls.sale_order.pec_id
        cls.pec.action_submit()
        pec_mgr = cls.pec.with_user(cls.user_manager)
        pec_mgr.action_approve()
        pec_mgr.action_create_invoices()
        cls.invoice_insurance = cls.pec.invoice_insurance_id
        cls.invoice_insurance.action_post()

        # Colonnes claim_sheet disponibles (chargées depuis le data XML)
        cls.columns_all = cls.Column.search([
            ('report_type', '=', 'claim_sheet'),
        ], order='sequence, id')

        cls.columns_ipm = cls.Column.search([
            ('report_type', '=', 'claim_sheet'),
            ('default_ipm', '=', True),
        ], order='sequence, id')

        cls.columns_insurance = cls.Column.search([
            ('report_type', '=', 'claim_sheet'),
            ('default_insurance', '=', True),
        ], order='sequence, id')

    def _create_wizard(self, **kwargs):
        """Helper : crée une instance du wizard avec les valeurs par défaut."""
        vals = {
            'insurer_id': self.insurer_ipm.id,
            'date_from': self.invoice_insurance.invoice_date.replace(day=1),
            'date_to': (self.invoice_insurance.invoice_date.replace(day=1) + relativedelta(months=1)) - timedelta(days=1),
        }
        vals.update(kwargs)
        return self.env['optical.claim.sheet.wizard'].create(vals)

    # --- AC #1 : Preset colonnes insurance ---

    def test_preset_columns_insurance(self):
        """Le onchange insurer_id pré-coche les colonnes default_insurance."""
        wizard = self._create_wizard(insurer_id=self.insurer_insurance.id)
        wizard._onchange_insurer_columns()
        self.assertTrue(wizard.report_column_ids)
        expected_names = set(self.columns_insurance.mapped('technical_name'))
        actual_names = set(wizard.report_column_ids.mapped('technical_name'))
        self.assertEqual(actual_names, expected_names)

    # --- AC #2 : Preset colonnes ipm ---

    def test_preset_columns_ipm(self):
        """Le onchange insurer_id pré-coche les colonnes default_ipm."""
        wizard = self._create_wizard()
        wizard._onchange_insurer_columns()
        self.assertTrue(wizard.report_column_ids)
        expected_names = set(self.columns_ipm.mapped('technical_name'))
        actual_names = set(wizard.report_column_ids.mapped('technical_name'))
        self.assertEqual(actual_names, expected_names)

    def test_onchange_no_insurer_clears_columns(self):
        """Le onchange sans insurer_id vide les colonnes."""
        wizard = self._create_wizard()
        wizard._onchange_insurer_columns()
        self.assertTrue(wizard.report_column_ids)
        wizard.insurer_id = False
        wizard._onchange_insurer_columns()
        self.assertFalse(wizard.report_column_ids)

    # --- AC #3 : Generation PDF avec colonnes dynamiques ---

    def test_generate_with_selected_columns(self):
        """La génération de bordereau avec colonnes sélectionnées ne provoque pas d'erreur."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        wizard.report_column_ids = [(6, 0, self.columns_ipm.ids)]
        result = wizard.action_generate()
        self.assertTrue(result)
        claim_sheet = self.invoice_insurance.claim_sheet_id
        self.assertTrue(claim_sheet)

    # --- AC #4 : Tracabilite colonnes sur claim_sheet ---

    def test_traceability_columns_on_claim_sheet(self):
        """Les colonnes sélectionnées sont stockées sur le claim_sheet après génération."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        wizard.report_column_ids = [(6, 0, self.columns_ipm.ids)]
        wizard.action_generate()
        claim_sheet = self.invoice_insurance.claim_sheet_id
        self.assertTrue(claim_sheet.column_ids)
        self.assertEqual(
            set(claim_sheet.column_ids.ids),
            set(self.columns_ipm.ids),
        )

    # --- AC #4 : Tracabilite sans colonnes explicites (fallback) ---

    def test_traceability_fallback_all_columns(self):
        """Sans colonnes sélectionnées, toutes les colonnes actives sont stockées."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        wizard.action_generate()
        claim_sheet = self.invoice_insurance.claim_sheet_id
        self.assertTrue(claim_sheet.column_ids)
        self.assertEqual(
            set(claim_sheet.column_ids.ids),
            set(self.columns_all.ids),
        )

    # --- AC #5 : Reimpression avec colonnes originales ---

    def test_reprint_uses_original_columns(self):
        """Le claim_sheet utilise ses column_ids originales pour la réimpression."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        wizard.report_column_ids = [(6, 0, self.columns_ipm.ids)]
        wizard.action_generate()
        claim_sheet = self.invoice_insurance.claim_sheet_id
        self.assertEqual(len(claim_sheet.column_ids), len(self.columns_ipm))
        rows = claim_sheet._get_dynamic_rows()
        self.assertTrue(rows)
        # Plus de ligne TOTAL GENERAL : la dernière ligne est un sous-total
        last_row = rows[-1]
        self.assertTrue(last_row.get('is_subtotal'))
        self.assertFalse(any(r.get('is_total') for r in rows))

    # --- AC #3 : Dynamic rows structure ---

    def test_dynamic_rows_structure(self):
        """Les rows dynamiques ont la bonne structure (values, sous-totaux)."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        wizard.report_column_ids = [(6, 0, self.columns_ipm.ids)]
        wizard.action_generate()
        claim_sheet = self.invoice_insurance.claim_sheet_id
        rows = claim_sheet._get_dynamic_rows()
        self.assertGreaterEqual(len(rows), 2)
        subtotal_rows = [r for r in rows if r.get('is_subtotal')]
        total_rows = [r for r in rows if r.get('is_total')]
        self.assertGreaterEqual(len(subtotal_rows), 1)
        self.assertEqual(len(total_rows), 0)
        n_cols = len(self.columns_ipm)
        for row in rows:
            self.assertEqual(len(row['values']), n_cols)

    # --- AC #3 : Column value mapping ---

    def test_column_value_mapping(self):
        """Le mapping _get_column_value retourne les bonnes valeurs."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        wizard.report_column_ids = [(6, 0, self.columns_ipm.ids)]
        wizard.action_generate()
        claim_sheet = self.invoice_insurance.claim_sheet_id
        col_date = self.Column.search([
            ('report_type', '=', 'claim_sheet'),
            ('technical_name', '=', 'date'),
        ], limit=1)
        col_ref = self.Column.search([
            ('report_type', '=', 'claim_sheet'),
            ('technical_name', '=', 'reference'),
        ], limit=1)
        invoice = self.invoice_insurance
        line = invoice.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product'
        )[:1]
        val_date = claim_sheet._get_column_value(col_date, invoice, line)
        val_ref = claim_sheet._get_column_value(col_ref, invoice, line)
        self.assertEqual(val_date, invoice.invoice_date)
        self.assertEqual(val_ref, invoice.name)

    # --- Data XML : colonnes chargees ---

    def test_data_columns_loaded(self):
        """Les colonnes claim_sheet sont chargées depuis le data XML."""
        self.assertGreaterEqual(len(self.columns_all), 11)
        tech_names = self.columns_all.mapped('technical_name')
        for name in ['date', 'reference', 'subscriber', 'participant',
                     'beneficiary', 'product_name', 'amount_total']:
            self.assertIn(name, tech_names)

    # --- Extension modele : champs default_insurance / default_ipm ---

    def test_default_insurance_ipm_fields_exist(self):
        """Les champs default_insurance et default_ipm sont accessibles."""
        col = self.columns_all[0]
        self.assertIn('default_insurance', col._fields)
        self.assertIn('default_ipm', col._fields)

    # --- Retrocompatibilite : bordereaux sans column_ids ---

    def test_retrocompat_empty_columns(self):
        """Un bordereau sans column_ids utilise le fallback (toutes colonnes actives)."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        wizard.report_column_ids = [(6, 0, self.columns_ipm.ids)]
        wizard.action_generate()
        claim_sheet = self.invoice_insurance.claim_sheet_id
        # Simuler un bordereau ancien sans column_ids
        claim_sheet.sudo().write({'column_ids': [(5, 0, 0)]})
        self.assertFalse(claim_sheet.column_ids)
        # _get_report_columns doit retourner le fallback
        fallback_cols = claim_sheet._get_report_columns()
        self.assertTrue(fallback_cols)
        self.assertEqual(set(fallback_cols.ids), set(self.columns_all.ids))
        # _get_dynamic_rows doit fonctionner avec le fallback
        rows = claim_sheet._get_dynamic_rows()
        self.assertTrue(rows)
        # Plus de ligne TOTAL GENERAL : la dernière ligne est un sous-total
        last_row = rows[-1]
        self.assertTrue(last_row.get('is_subtotal'))

    # --- M2 : Test rendu QWeb HTML ---

    def test_qweb_html_rendering(self):
        """Le rendu QWeb HTML du bordereau avec colonnes dynamiques ne provoque pas d'erreur."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        wizard.report_column_ids = [(6, 0, self.columns_ipm.ids)]
        wizard.action_generate()
        claim_sheet = self.invoice_insurance.claim_sheet_id
        report = self.env.ref('optical.action_report_claim_sheet')
        html_content = report._render_qweb_html(
            'optical.report_claim_sheet_document', claim_sheet.ids,
        )
        self.assertTrue(html_content)
        self.assertTrue(html_content[0])

    # ===================================================================
    # Story 13-3 : Profils de colonnes sauvegardables
    # ===================================================================

    # --- 6.1 : Test sauvegarde profil ---

    def test_save_profile(self):
        """action_save_profile crée un profil pour l'assureur sélectionné."""
        wizard = self._create_wizard()
        wizard._onchange_insurer_columns()
        self.assertTrue(wizard.report_column_ids)
        self.assertFalse(wizard.has_profile)

        result = wizard.action_save_profile()
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertEqual(result['tag'], 'display_notification')

        # Vérifier la création du profil
        profile = wizard.profile_id
        self.assertTrue(profile)
        self.assertTrue(wizard.has_profile)  # M2: verify computed field
        self.assertEqual(profile.name, self.insurer_ipm.name)
        self.assertEqual(profile.report_type, 'claim_sheet')
        self.assertEqual(profile.partner_id, self.insurer_ipm)
        self.assertEqual(
            set(profile.column_ids.ids),
            set(wizard.report_column_ids.ids),
        )

    # --- 6.2 : Test chargement automatique profil ---

    def test_auto_load_profile(self):
        """Le onchange charge automatiquement le profil si un profil partner existe."""
        Profile = self.env['report.dynamic.column.profile']
        profile = Profile.create({
            'name': 'Profil IPM Test',
            'report_type': 'claim_sheet',
            'partner_id': self.insurer_ipm.id,
            'column_ids': [Command.set(self.columns_ipm[:3].ids)],
        })

        wizard = self._create_wizard()
        wizard._onchange_insurer_columns()

        self.assertEqual(wizard.profile_id, profile)
        self.assertEqual(
            set(wizard.report_column_ids.ids),
            set(self.columns_ipm[:3].ids),
        )

    # --- 6.3 : Test fallback sans profil ---

    def test_fallback_no_profile(self):
        """Sans profil, le onchange utilise les flags default_insurance/default_ipm."""
        # Pas de profil créé pour insurer_insurance
        wizard = self._create_wizard(insurer_id=self.insurer_insurance.id)
        wizard._onchange_insurer_columns()

        self.assertFalse(wizard.profile_id)
        expected_names = set(self.columns_insurance.mapped('technical_name'))
        actual_names = set(wizard.report_column_ids.mapped('technical_name'))
        self.assertEqual(actual_names, expected_names)

    # --- 6.4 : Test mise a jour profil ---

    def test_update_profile(self):
        """action_update_profile met à jour les colonnes du profil existant."""
        Profile = self.env['report.dynamic.column.profile']
        profile = Profile.create({
            'name': 'Profil MAJ Test',
            'report_type': 'claim_sheet',
            'partner_id': self.insurer_ipm.id,
            'column_ids': [Command.set(self.columns_ipm[:2].ids)],
        })

        wizard = self._create_wizard()
        wizard._onchange_insurer_columns()
        self.assertEqual(wizard.profile_id, profile)

        # Modifier les colonnes du wizard
        wizard.report_column_ids = [(6, 0, self.columns_all.ids)]
        result = wizard.action_update_profile()
        self.assertEqual(result['type'], 'ir.actions.client')

        # Vérifier que le profil est mis à jour
        self.assertEqual(
            set(profile.column_ids.ids),
            set(self.columns_all.ids),
        )

    # --- 6.5 : Test colonnes modifiees sans sauvegarde ---

    def test_modified_columns_without_save(self):
        """Modifier colonnes sans sauvegarder ne modifie pas le profil existant."""
        Profile = self.env['report.dynamic.column.profile']
        original_cols = self.columns_ipm[:3]
        profile = Profile.create({
            'name': 'Profil Inchangé Test',
            'report_type': 'claim_sheet',
            'partner_id': self.insurer_ipm.id,
            'column_ids': [Command.set(original_cols.ids)],
        })

        wizard = self._create_wizard()
        wizard._onchange_insurer_columns()
        self.assertEqual(wizard.profile_id, profile)

        # Modifier les colonnes du wizard sans appeler action_update_profile
        wizard.report_column_ids = [(6, 0, self.columns_all.ids)]

        # Générer le bordereau
        wizard.action_search_invoices()
        wizard.action_generate()

        # Le profil doit être inchangé
        self.assertEqual(
            set(profile.column_ids.ids),
            set(original_cols.ids),
        )

    # --- 6.6 : Test has_profile computed ---

    def test_has_profile_computed(self):
        """has_profile est True quand profile_id est défini."""
        wizard = self._create_wizard()
        wizard._onchange_insurer_columns()
        self.assertFalse(wizard.has_profile)

        Profile = self.env['report.dynamic.column.profile']
        Profile.create({
            'name': 'Profil Has Test',
            'report_type': 'claim_sheet',
            'partner_id': self.insurer_ipm.id,
            'column_ids': [Command.set(self.columns_ipm.ids)],
        })
        wizard._onchange_insurer_columns()
        self.assertTrue(wizard.has_profile)

    # --- 6.7 : Test onchange clear profile ---

    def test_onchange_clear_insurer_clears_profile(self):
        """Le onchange sans insurer_id vide aussi profile_id."""
        Profile = self.env['report.dynamic.column.profile']
        Profile.create({
            'name': 'Profil Clear Test',
            'report_type': 'claim_sheet',
            'partner_id': self.insurer_ipm.id,
            'column_ids': [Command.set(self.columns_ipm.ids)],
        })

        wizard = self._create_wizard()
        wizard._onchange_insurer_columns()
        self.assertTrue(wizard.profile_id)

        wizard.insurer_id = False
        wizard._onchange_insurer_columns()
        self.assertFalse(wizard.profile_id)
        self.assertFalse(wizard.report_column_ids)

    # --- Review: H1 — Protection doublons profil ---

    def test_save_profile_no_duplicate(self):
        """action_save_profile met à jour un profil existant au lieu de créer un doublon."""
        Profile = self.env['report.dynamic.column.profile']
        existing = Profile.create({
            'name': 'Profil Existant',
            'report_type': 'claim_sheet',
            'partner_id': self.insurer_ipm.id,
            'column_ids': [Command.set(self.columns_ipm[:2].ids)],
        })
        initial_count = Profile.search_count([
            ('report_type', '=', 'claim_sheet'),
            ('partner_id', '=', self.insurer_ipm.id),
        ])

        wizard = self._create_wizard()
        wizard._onchange_insurer_columns()
        # Modifier les colonnes puis sauvegarder
        wizard.report_column_ids = [(6, 0, self.columns_all.ids)]
        wizard.profile_id = False  # Simuler absence de profil chargé
        wizard.action_save_profile()

        # Pas de doublon
        final_count = Profile.search_count([
            ('report_type', '=', 'claim_sheet'),
            ('partner_id', '=', self.insurer_ipm.id),
        ])
        self.assertEqual(final_count, initial_count)
        # Le profil existant est mis à jour
        self.assertEqual(
            set(existing.column_ids.ids),
            set(self.columns_all.ids),
        )

    # --- Review: M3 — Test erreurs UserError ---

    def test_save_profile_error_no_columns(self):
        """action_save_profile lève UserError sans colonnes."""
        from odoo.exceptions import UserError
        wizard = self._create_wizard()
        wizard.report_column_ids = False
        with self.assertRaises(UserError):
            wizard.action_save_profile()

    def test_update_profile_error_no_profile(self):
        """action_update_profile lève UserError sans profil."""
        from odoo.exceptions import UserError
        wizard = self._create_wizard()
        wizard.profile_id = False
        with self.assertRaises(UserError):
            wizard.action_update_profile()

    # --- Review: L2 — Test profil par defaut global ---

    def test_default_global_profile_fallback(self):
        """Un profil par défaut global est chargé avant les flags type assureur."""
        Profile = self.env['report.dynamic.column.profile']
        global_profile = Profile.create({
            'name': 'Profil Global Défaut',
            'report_type': 'claim_sheet',
            'partner_id': False,
            'is_default': True,
            'column_ids': [Command.set(self.columns_ipm[:2].ids)],
        })

        # Assureur insurance sans profil spécifique
        wizard = self._create_wizard(insurer_id=self.insurer_insurance.id)
        wizard._onchange_insurer_columns()

        # Le profil global est chargé (pas les flags default_insurance)
        self.assertEqual(wizard.profile_id, global_profile)
        self.assertEqual(
            set(wizard.report_column_ids.ids),
            set(self.columns_ipm[:2].ids),
        )
