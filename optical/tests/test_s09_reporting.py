# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestOpticalSaleReport(OpticalTestCommon):
    """Tests Story 9.1 : SQL view optical.sale.report."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Définir optical_type sur les produits
        cls.product_monture.product_tmpl_id.optical_type = 'frame'
        cls.product_verre.product_tmpl_id.optical_type = 'lens'

        # Attributs monture (Story 9.4)
        cls.frame_material = cls.env['optical.frame.material'].create(
            {'name': 'Acetate', 'sequence': 1})
        cls.frame_color = cls.env['optical.frame.color'].create(
            {'name': 'Noir', 'sequence': 1})
        cls.product_monture.product_tmpl_id.write({
            'frame_shape': 'rectangular',
            'frame_gender': 'mixed',
            'frame_rim_type': 'full_rim',
            'frame_material_ids': [Command.set([cls.frame_material.id])],
            'frame_color_ids': [Command.set([cls.frame_color.id])],
        })

        # Attributs verre (Story 9.4)
        cls.lens_treatment = cls.env['optical.lens.treatment'].create(
            {'name': 'Anti-reflet', 'sequence': 1})
        cls.lens_tint = cls.env['optical.lens.tint'].create(
            {'name': 'Photochromique', 'sequence': 1})
        cls.lens_index_167 = cls.env['optical.lens.index'].create(
            {'name': '1.67', 'value': 1.67})
        cls.product_verre.product_tmpl_id.write({
            'lens_design': 'progressive',
            'lens_material': 'organic',
            'lens_surface': 'aspherical',
            'lens_index_id': cls.lens_index_167.id,
            'lens_treatment_ids': [Command.set([cls.lens_treatment.id])],
            'lens_tint_ids': [Command.set([cls.lens_tint.id])],
        })

        # Assigner prescription et policy sur la commande
        cls.sale_order.write({
            'policy_id': cls.policy.id,
            'prescription_id': cls.prescription_confirmed.id,
        })

        # Créer une facture assurance postée via le workflow PEC complet
        pec = cls._approve_pec()
        pec.with_user(cls.user_responsable).action_create_invoices()
        cls.pec = pec
        cls.invoice_insurance = pec.invoice_insurance_id
        cls.invoice_insurance.action_post()

    def test_01_sql_view_exists(self):
        """AC#1 / AC#12 : La table optical_sale_report existe dans la base."""
        self.env.cr.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'optical_sale_report'
            )
        """)
        exists = self.env.cr.fetchone()[0]
        self.assertTrue(exists, "La SQL view optical_sale_report doit exister")

    def test_02_invoice_appears_in_report(self):
        """AC#1 / AC#12 : La facture assurance postée apparaît dans le rapport."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
        ])
        self.assertTrue(report, "La facture assurance doit apparaître dans le rapport")

    def test_03_dimensions_insurer(self):
        """AC#2 / AC#12 : La dimension assureur est correcte."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
        ])
        for line in report:
            self.assertEqual(
                line.insurer_id, self.insurer,
                "L'assureur doit être l'IPM de la police",
            )

    def test_04_dimensions_prescriber(self):
        """AC#3 / AC#12 : La dimension prescripteur est correcte."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
        ])
        for line in report:
            self.assertEqual(
                line.prescriber_id, self.prescriber,
                "Le prescripteur doit correspondre à l'ordonnance",
            )

    def test_05_dimensions_subscriber(self):
        """AC#4 / AC#12 : La dimension souscripteur est correcte."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
        ])
        for line in report:
            self.assertEqual(
                line.subscriber_id, self.subscriber,
                "Le souscripteur doit correspondre à la police",
            )

    def test_06_dimensions_optical_type(self):
        """AC#5 / AC#12 : La dimension type produit est correcte."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
        ])
        optical_types = set(report.mapped('optical_type'))
        self.assertIn('frame', optical_types, "Le type monture doit être présent")
        self.assertIn('lens', optical_types, "Le type verre doit être présent")

    def test_08_measures_amount(self):
        """AC#12 : Les mesures montant sont correctes."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
        ])
        total_ttc = sum(report.mapped('amount_total'))
        # La facture assurance ne contient que la part assurance (coverage)
        self.assertGreater(total_ttc, 0, "Le montant TTC total doit être positif")

    def test_09_measures_quantity(self):
        """AC#12 : Les mesures quantite sont correctes."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
        ])
        total_qty = sum(report.mapped('product_qty'))
        self.assertGreater(total_qty, 0, "La quantité totale doit être positive")

    def test_10_nbr_count(self):
        """AC#12 : Le compteur nbr est correct (1 par ligne)."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
        ])
        for line in report:
            self.assertEqual(line.nbr, 1, "Chaque ligne doit avoir nbr=1")

    def test_12_filter_by_period(self):
        """AC#7 / AC#12 : Le filtre par periode fonctionne."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
        ])
        # Vérifier que date, month, year sont remplis
        for line in report:
            self.assertTrue(line.date, "La date doit être remplie")
            self.assertTrue(line.month, "Le mois doit être rempli")
            self.assertTrue(line.year, "L'année doit être remplie")

    def test_13_posted_insurance_invoices_in_report(self):
        """AC#1 : Les factures assurance postées apparaissent dans le rapport."""
        # Les lignes du rapport pour cette PEC proviennent de account_move_line
        # (l'id du rapport = l'id de la ligne de facture)
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
        ])
        report_line_ids = set(report.ids)
        # Les lignes produit de la facture assurance doivent être dans le rapport
        insurance_product_lines = self.invoice_insurance.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product'
        )
        self.assertTrue(insurance_product_lines, "La facture assurance doit avoir des lignes produit")
        for line in insurance_product_lines:
            self.assertIn(
                line.id, report_line_ids,
                "Les lignes de la facture assurance doivent être dans le rapport",
            )
        # Les lignes du TM (brouillon) ne doivent PAS être dans le rapport
        if self.pec.invoice_tm_id:
            tm_product_lines = self.pec.invoice_tm_id.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product'
            )
            for line in tm_product_lines:
                self.assertNotIn(
                    line.id, report_line_ids,
                    "Les lignes du TM (brouillon) ne doivent PAS être dans le rapport",
                )

    def test_14_acl_read_only(self):
        """AC#11 : Lecture autorisee, creation/ecriture/suppression interdites."""
        Report = self.env['optical.sale.report']

        # Vendeur peut lire
        report_vendeur = Report.with_user(self.user_vendeur).search([])
        self.assertIsNotNone(report_vendeur, "Le vendeur doit pouvoir lire le rapport")

        # Responsable peut lire
        report_manager = Report.with_user(self.user_responsable).search([])
        self.assertIsNotNone(report_manager, "Le responsable doit pouvoir lire le rapport")

        # Vendeur ne peut PAS créer/écrire/supprimer
        with self.assertRaises(AccessError):
            Report.with_user(self.user_vendeur).create({})
        if report_vendeur:
            with self.assertRaises(AccessError):
                report_vendeur[0].with_user(self.user_vendeur).write({'amount_total': 0})
            with self.assertRaises(AccessError):
                report_vendeur[0].with_user(self.user_vendeur).unlink()

        # Responsable ne peut PAS créer/écrire/supprimer
        with self.assertRaises(AccessError):
            Report.with_user(self.user_responsable).create({})
        if report_manager:
            with self.assertRaises(AccessError):
                report_manager[0].with_user(self.user_responsable).write({'amount_total': 0})
            with self.assertRaises(AccessError):
                report_manager[0].with_user(self.user_responsable).unlink()

    def test_15_patient_dimension(self):
        """AC#1 : La dimension patient vient de la PEC (pas du partner de la facture)."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
        ])
        for line in report:
            self.assertEqual(
                line.patient_id, self.patient,
                "Le patient doit venir de la PEC, pas du partner de la facture assurance",
            )

    def test_16_views_are_valid(self):
        """AC#8 / AC#10 : Les vues pivot, graph, list et search sont valides."""
        Report = self.env['optical.sale.report']
        for view_type in ('pivot', 'graph', 'list', 'search'):
            view = Report.get_view(view_type=view_type)
            self.assertTrue(view, "La vue %s doit exister" % view_type)

    def test_17_actions_exist(self):
        """AC#10 : Les 4 actions window avec search_default existent."""
        for xmlid in (
            'optical.optical_sale_report_action_insurer',
            'optical.optical_sale_report_action_prescriber',
            'optical.optical_sale_report_action_subscriber',
            'optical.optical_sale_report_action_product',
        ):
            action = self.env.ref(xmlid)
            self.assertEqual(action.res_model, 'optical.sale.report')

    def test_18_menus_exist(self):
        """AC#10 : Le menu Rapports et ses 4 sous-menus existent."""
        parent = self.env.ref('optical.menu_optical_rapports')
        self.assertTrue(parent, "Le menu parent Rapports doit exister")
        for xmlid in (
            'optical.menu_optical_report_insurer',
            'optical.menu_optical_report_prescriber',
            'optical.menu_optical_report_subscriber',
            'optical.menu_optical_report_product',
        ):
            menu = self.env.ref(xmlid)
            self.assertEqual(
                menu.parent_id, parent,
                "Le sous-menu %s doit etre enfant de Rapports" % xmlid,
            )

    # ==========================================
    # Story 9-2 : Filtres OU et periode
    # ==========================================

    def test_25_report_search_has_date_filter(self):
        """S9-2 AC#8 : La search view rapport pivot contient le filtre date natif."""
        view = self.env.ref('optical.optical_sale_report_search')
        arch = view.arch
        self.assertIn('filter_date', arch,
                       "La search view rapport doit contenir le filtre date natif")

    def test_26_report_search_has_quarter_groupby(self):
        """S9-2 AC#8 : La search view rapport pivot contient le groupement par trimestre."""
        view = self.env.ref('optical.optical_sale_report_search')
        arch = view.arch
        self.assertIn('date:quarter', arch,
                       "La search view rapport doit contenir le groupement par trimestre")

    def test_29_filter_report_by_date_range(self):
        """S9-2 AC#2 : Le filtrage par plage de dates fonctionne sur le rapport."""
        from datetime import date, timedelta
        today = date.today()

        # Toutes les lignes du rapport doivent avoir une date
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
        ])
        self.assertTrue(report, "Le rapport doit contenir des lignes")

        # Filtre par date >= début du mois courant (assertion positive)
        first_day = today.replace(day=1)
        report_month = self.env['optical.sale.report'].search([
            ('date', '>=', first_day),
            ('pec_id', '=', self.pec.id),
        ])
        self.assertTrue(report_month,
                        "Les lignes du mois courant doivent apparaître dans le rapport")

        # Filtre par date dans le futur — aucune ligne ne doit apparaître (assertion négative)
        future_date = today + timedelta(days=365)
        report_future = self.env['optical.sale.report'].search([
            ('date', '>=', future_date),
            ('pec_id', '=', self.pec.id),
        ])
        self.assertFalse(report_future,
                         "Aucune ligne ne doit apparaître pour une date dans le futur")

    # ==========================================
    # Story 9-4 : Proprietes produit et filtre assurance
    # ==========================================

    def test_30_frame_shape_dimension(self):
        """S9-4 AC#1 : La dimension frame_shape est remplie pour les montures."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
            ('optical_type', '=', 'frame'),
        ])
        self.assertTrue(report, "Des lignes monture doivent exister")
        for line in report:
            self.assertEqual(line.frame_shape, 'rectangular',
                             "La forme monture doit être rectangular")

    def test_31_frame_gender_dimension(self):
        """S9-4 AC#1 : La dimension frame_gender est remplie pour les montures."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
            ('optical_type', '=', 'frame'),
        ])
        for line in report:
            self.assertEqual(line.frame_gender, 'mixed',
                             "Le genre monture doit être mixed")

    def test_32_frame_rim_type_dimension(self):
        """S9-4 AC#1 : La dimension frame_rim_type est remplie pour les montures."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
            ('optical_type', '=', 'frame'),
        ])
        for line in report:
            self.assertEqual(line.frame_rim_type, 'full_rim',
                             "Le type cerclage doit être full_rim")

    def test_33_lens_design_dimension(self):
        """S9-4 AC#1 : La dimension lens_design est remplie pour les verres."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
            ('optical_type', '=', 'lens'),
        ])
        self.assertTrue(report, "Des lignes verre doivent exister")
        for line in report:
            self.assertEqual(line.lens_design, 'progressive',
                             "Le design verre doit être progressive")

    def test_34_lens_material_dimension(self):
        """S9-4 AC#1 : La dimension lens_material est remplie pour les verres."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
            ('optical_type', '=', 'lens'),
        ])
        for line in report:
            self.assertEqual(line.lens_material, 'organic',
                             "Le materiau verre doit etre organic")

    def test_35_lens_surface_dimension(self):
        """S9-4 AC#1 : La dimension lens_surface est remplie pour les verres."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
            ('optical_type', '=', 'lens'),
        ])
        for line in report:
            self.assertEqual(line.lens_surface, 'aspherical',
                             "La surface verre doit etre aspherical")

    def test_36_lens_index_dimension(self):
        """S9-4 AC#1 : La dimension lens_index est remplie pour les verres."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
            ('optical_type', '=', 'lens'),
        ])
        for line in report:
            self.assertTrue(line.lens_index,
                            "L'indice de refraction doit etre rempli")
            self.assertIn('1.67', line.lens_index,
                          "L'indice de refraction doit contenir 1.67")

    def test_37_frame_materials_aggregated(self):
        """S9-4 AC#1 : Les materiaux monture sont agreges via string_agg."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
            ('optical_type', '=', 'frame'),
        ])
        for line in report:
            self.assertEqual(line.frame_materials, 'Acetate',
                             "Les materiaux monture doivent contenir Acetate")

    def test_38_frame_colors_aggregated(self):
        """S9-4 AC#1 : Les couleurs monture sont agregées via string_agg."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
            ('optical_type', '=', 'frame'),
        ])
        for line in report:
            self.assertEqual(line.frame_colors, 'Noir',
                             "Les couleurs monture doivent contenir Noir")

    def test_39_lens_treatments_aggregated(self):
        """S9-4 AC#1 : Les traitements verre sont agreges via string_agg."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
            ('optical_type', '=', 'lens'),
        ])
        for line in report:
            self.assertEqual(line.lens_treatments, 'Anti-reflet',
                             "Les traitements verre doivent contenir Anti-reflet")

    def test_40_lens_tints_aggregated(self):
        """S9-4 AC#1 : Les teintes verre sont agregées via string_agg."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
            ('optical_type', '=', 'lens'),
        ])
        for line in report:
            self.assertEqual(line.lens_tints, 'Photochromique',
                             "Les teintes verre doivent contenir Photochromique")

    def test_41_is_insurance_invoice_field(self):
        """S9-4 AC#2 : Le champ is_insurance_invoice est rempli sur les lignes assurance."""
        report = self.env['optical.sale.report'].search([
            ('pec_id', '=', self.pec.id),
        ])
        for line in report:
            self.assertTrue(line.is_insurance_invoice,
                            "Les lignes de facture assurance doivent avoir is_insurance_invoice=True")

    def test_42_filter_insurance_only(self):
        """S9-4 AC#2 : Le filtre is_insurance_invoice fonctionne."""
        # Creer une facture hors assurance (vente directe)
        direct_invoice = self.env['account.move'].sudo().create({
            'move_type': 'out_invoice',
            'partner_id': self.patient.id,
            'invoice_line_ids': [Command.create({
                'product_id': self.product_monture.id,
                'quantity': 1,
                'price_unit': 30000.0,
            })],
        })
        direct_invoice.action_post()

        # Sans filtre : les deux factures apparaissent
        all_report = self.env['optical.sale.report'].search([])
        insurance_lines = all_report.filtered(lambda l: l.is_insurance_invoice)
        non_insurance_lines = all_report.filtered(lambda l: not l.is_insurance_invoice)
        self.assertTrue(insurance_lines, "Des lignes assurance doivent exister")
        self.assertTrue(non_insurance_lines, "Des lignes hors assurance doivent exister")

        # Avec filtre assurance : seules les factures assurance
        report_insurance = self.env['optical.sale.report'].search([
            ('is_insurance_invoice', '=', True),
        ])
        for line in report_insurance:
            self.assertTrue(line.is_insurance_invoice,
                            "Le filtre assurance doit renvoyer uniquement les factures assurance")

        # La facture directe ne doit PAS apparaitre avec le filtre assurance
        direct_line_ids = set(direct_invoice.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product'
        ).ids)
        report_insurance_ids = set(report_insurance.ids)
        self.assertFalse(
            direct_line_ids & report_insurance_ids,
            "La facture directe ne doit pas apparaitre avec le filtre assurance",
        )

    def test_43_all_sales_without_filter(self):
        """S9-4 AC#2 : Sans filtre, toutes les factures postées apparaissent."""
        # Creer une facture hors assurance
        direct_invoice = self.env['account.move'].sudo().create({
            'move_type': 'out_invoice',
            'partner_id': self.patient.id,
            'invoice_line_ids': [Command.create({
                'product_id': self.product_monture.id,
                'quantity': 1,
                'price_unit': 25000.0,
            })],
        })
        direct_invoice.action_post()

        # La facture directe doit apparaitre dans le rapport (sans filtre)
        direct_product_lines = direct_invoice.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product'
        )
        report_all = self.env['optical.sale.report'].search([])
        report_ids = set(report_all.ids)
        for line in direct_product_lines:
            self.assertIn(line.id, report_ids,
                          "La facture directe doit apparaitre dans le rapport sans filtre")

    def test_44_action_product_props_exists(self):
        """S9-4 AC#4 : L'action 'Ventes par proprietes produit' existe."""
        action = self.env.ref('optical.optical_sale_report_action_product_props')
        self.assertEqual(action.res_model, 'optical.sale.report')
        ctx = eval(action.context)
        self.assertEqual(ctx.get('search_default_group_optical_type'), 1,
                         "L'action doit avoir search_default_group_optical_type")
        self.assertEqual(ctx.get('search_default_group_frame_shape'), 1,
                         "L'action doit avoir search_default_group_frame_shape")
        self.assertFalse(ctx.get('search_default_filter_insurance'),
                         "L'action ne doit PAS avoir search_default_filter_insurance")

    def test_45_existing_actions_have_insurance_filter(self):
        """S9-4 AC#3 : Les 4 actions existantes ont search_default_filter_insurance."""
        for xmlid in (
            'optical.optical_sale_report_action_insurer',
            'optical.optical_sale_report_action_prescriber',
            'optical.optical_sale_report_action_subscriber',
            'optical.optical_sale_report_action_product',
        ):
            action = self.env.ref(xmlid)
            ctx = eval(action.context)
            self.assertEqual(ctx.get('search_default_filter_insurance'), 1,
                             "%s doit avoir search_default_filter_insurance=1" % xmlid)

    def test_46_search_view_has_insurance_filter(self):
        """S9-4 AC#2 : La search view contient le filtre 'Factures assurance'."""
        view = self.env.ref('optical.optical_sale_report_search')
        arch = view.arch
        self.assertIn('filter_insurance', arch,
                       "La search view doit contenir le filtre filter_insurance")

    def test_47_search_view_has_product_groupbys(self):
        """S9-4 AC#5 : La search view contient les groupements proprietes produit."""
        view = self.env.ref('optical.optical_sale_report_search')
        arch = view.arch
        for groupby_name in ('group_frame_shape', 'group_frame_gender',
                             'group_lens_design', 'group_lens_material'):
            self.assertIn(groupby_name, arch,
                          "La search view doit contenir le groupement %s" % groupby_name)

    def test_48_menu_product_props_exists(self):
        """S9-4 AC#4 : Le sous-menu 'Ventes par proprietes produit' existe."""
        parent = self.env.ref('optical.menu_optical_rapports')
        menu = self.env.ref('optical.menu_optical_report_product_props')
        self.assertEqual(menu.parent_id, parent,
                         "Le sous-menu doit etre enfant de Rapports")
