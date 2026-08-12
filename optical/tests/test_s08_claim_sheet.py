# -*- coding: utf-8 -*-
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Date
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestClaimSheetWizard(OpticalTestCommon):
    """Tests Story 8-1 : Wizard génération bordereau et sélection factures."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Donner le type assureur IPM à l'insurer de test
        cls.insurer.insurer_type = 'ipm'

        # Définir optical_type sur les produits (testabilité TVA inline montures)
        cls.product_monture.product_tmpl_id.optical_type = 'frame'
        cls.product_verre.product_tmpl_id.optical_type = 'lens'

        # Créer des factures assurance via le workflow PEC complet
        pec = cls._approve_pec()
        pec.with_user(cls.user_responsable).action_create_invoices()
        cls.pec = pec
        cls.invoice_insurance = pec.invoice_insurance_id
        cls.invoice_tm = pec.invoice_tm_id
        # Poster les factures
        cls.invoice_insurance.action_post()
        cls.invoice_tm.action_post()

    def _create_wizard(self, user=None, **kwargs):
        """Helper : crée une instance du wizard avec les valeurs par défaut."""
        user = user or self.user_responsable
        inv_date = self.invoice_insurance.invoice_date
        first_day = inv_date.replace(day=1)
        last_day = (first_day + relativedelta(months=1)) - timedelta(days=1)
        vals = {
            'insurer_id': self.insurer.id,
            'date_from': first_day,
            'date_to': last_day,
        }
        vals.update(kwargs)
        return self.env['optical.claim.sheet.wizard'].with_user(user).create(vals)

    def _generate_claim_sheet(self, wizard):
        """Helper : génère le bordereau via le wizard et retourne le claim_sheet."""
        wizard.action_generate()
        claim_sheet = self.invoice_insurance.claim_sheet_id
        if not claim_sheet:
            # Chercher via les factures du wizard
            claim_sheet = wizard.invoice_ids[0].claim_sheet_id
        return claim_sheet

    # --- Task 6.2 : Test recherche factures ---

    def test_search_invoices_finds_eligible(self):
        """Le wizard trouve les factures assurance éligibles pour l'IPM et la période."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        self.assertIn(self.invoice_insurance, wizard.invoice_ids)

    # --- Task 6.3 : Test aucune facture ---

    def test_search_invoices_no_results_raises(self):
        """UserError si aucune facture éligible pour l'assureur/période."""
        other_insurer = self.env['res.partner'].create({
            'name': 'Autre IPM',
            'is_insurer': True,
            'insurer_type': 'ipm',
        })
        wizard = self._create_wizard(insurer_id=other_insurer.id)
        with self.assertRaises(UserError):
            wizard.action_search_invoices()

    # --- Task 6.4 : Test generation et marquage ---

    def test_generate_marks_invoices_sent(self):
        """Après génération, les factures sont marquées insurance_sent=True avec date du jour."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        result = wizard.action_generate()
        self.assertTrue(self.invoice_insurance.insurance_sent)
        self.assertEqual(self.invoice_insurance.insurance_sent_date, Date.today())
        # Vérifie que l'action retourne un rapport PDF
        self.assertEqual(result.get('type'), 'ir.actions.report')

    def test_generate_without_search_raises(self):
        """Générer sans avoir cherché les factures lève UserError."""
        wizard = self._create_wizard()
        with self.assertRaises(UserError):
            wizard.action_generate()

    # --- Task 6.5 : Test filtrage par mois ---

    def test_filter_by_month(self):
        """Seules les factures du mois sélectionné apparaissent."""
        # Créer une 2e facture dans un mois différent
        order2 = self.env['sale.order'].create({
            'partner_id': self.patient.id,
            'policy_id': self.policy.id,
            'order_line': [
                Command.create({
                    'product_id': self.product_monture.id,
                    'product_uom_qty': 1,
                    'price_unit': 40000.0,
                }),
            ],
        })
        order2.action_create_pec()
        order2.action_confirm()
        pec2 = order2.pec_id
        pec2.action_submit()
        pec2.with_user(self.user_responsable).action_approve()
        pec2.write({'amount_insurance_approved': order2.amount_insurance or order2.amount_total})
        pec2.with_user(self.user_responsable).action_create_invoices()
        invoice2 = pec2.invoice_insurance_id
        invoice2.action_post()

        # Déplacer invoice2 à un autre mois (button_draft → changer date → repost)
        current_date = self.invoice_insurance.invoice_date
        other_month_date = current_date + relativedelta(months=1)
        invoice2.button_draft()
        invoice2.write({'invoice_date': other_month_date})
        invoice2.action_post()

        # Wizard pour le mois courant
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        self.assertIn(self.invoice_insurance, wizard.invoice_ids)
        self.assertNotIn(invoice2, wizard.invoice_ids)

    # --- Task 6.6 : Test filtrage par OU ---

    # --- Task 6.7 : Test factures deja envoyées exclues ---

    def test_already_sent_invoices_excluded(self):
        """Les factures déjà marquées insurance_sent=True sont exclues."""
        self.invoice_insurance.sudo().write({
            'insurance_sent': True,
            'insurance_sent_date': Date.today(),
        })
        wizard = self._create_wizard()
        with self.assertRaises(UserError):
            wizard.action_search_invoices()

    # --- Task 6.8 : Test insurer_type ---

    def test_insurer_type_field_exists(self):
        """Le champ insurer_type existe sur res.partner et accepte les bonnes valeurs."""
        self.insurer.insurer_type = 'insurance'
        self.assertEqual(self.insurer.insurer_type, 'insurance')
        self.insurer.insurer_type = 'ipm'
        self.assertEqual(self.insurer.insurer_type, 'ipm')

    # --- Task 6.9 : Test securite ---

    def test_vendeur_cannot_create_wizard(self):
        """Un vendeur ne peut PAS creer un wizard (pas de droit create)."""
        with self.assertRaises(AccessError):
            self._create_wizard(user=self.user_vendeur)

    # --- Task 6.10 : Test NFR15 non-regression ---

    def test_non_insurance_invoices_unaffected(self):
        """Les factures non-assurance ne sont pas incluses dans le wizard."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        self.assertNotIn(self.invoice_tm, wizard.invoice_ids)

    # --- Review fix H2 : Tests _get_invoices_grouped (AC4) ---
    # Note Story 8-3 : _get_invoices_grouped migre vers optical.claim.sheet

    def test_get_invoices_grouped_ipm_format(self):
        """Format IPM : regroupement par patient/beneficiaire (AC4)."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        claim_sheet = self._generate_claim_sheet(wizard)
        groups = claim_sheet._get_invoices_grouped()
        self.assertTrue(groups, "Au moins un groupe doit exister")
        group = groups[0]
        # En format IPM, group_label = patient
        self.assertEqual(group['group_label'], self.patient.name)
        self.assertTrue(group['invoices'])
        self.assertGreater(group['subtotal'], 0)

    def test_get_invoices_grouped_insurance_format(self):
        """Format Assurance : regroupement par souscripteur/employeur (AC4)."""
        self.insurer.insurer_type = 'insurance'
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        claim_sheet = self._generate_claim_sheet(wizard)
        groups = claim_sheet._get_invoices_grouped()
        self.assertTrue(groups, "Au moins un groupe doit exister")
        group = groups[0]
        # En format Assurance, group_label = souscripteur
        self.assertEqual(group['group_label'], self.subscriber.name)
        self.assertTrue(group['invoices'])
        self.assertGreater(group['subtotal'], 0)

    # --- Review fix H2 : Test rendu PDF reel ---

    def test_render_claim_sheet_pdf(self):
        """Le template QWeb du bordereau se rend sans erreur (AC3)."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        claim_sheet = self._generate_claim_sheet(wizard)
        report = self.env.ref('optical.action_report_claim_sheet')
        content, content_type = report._render_qweb_pdf(report.id, claim_sheet.ids)
        self.assertTrue(content, "Le rendu du bordereau ne doit pas etre vide")
        self.assertIn(content_type, ('pdf', 'html'))

    # --- Task 6.11 : Test flux complet bout en bout ---

    def test_full_flow_end_to_end(self):
        """Flux complet : recherche → generation → re-recherche leve UserError."""
        wizard1 = self._create_wizard()
        wizard1.action_search_invoices()
        self.assertTrue(wizard1.invoice_ids)
        wizard1.action_generate()
        # Toutes les factures sont desormais insurance_sent=True
        self.assertTrue(self.invoice_insurance.insurance_sent)
        # Nouveau wizard pour le meme IPM/mois → aucune facture
        wizard2 = self._create_wizard()
        with self.assertRaises(UserError):
            wizard2.action_search_invoices()

    # ================================================================
    # Story 8-2 : Tests validation contenu PDF deux formats
    # ================================================================

    def _render_html(self, claim_sheet):
        """Helper : rend le bordereau en HTML et retourne la string décodée.

        Story 8-3 : le rapport pointe vers optical.claim.sheet (pas le wizard).
        """
        report = self.env.ref('optical.action_report_claim_sheet')
        html_content, content_type = report._render_qweb_html(report.id, claim_sheet.ids)
        return html_content.decode('utf-8')

    def _create_posted_invoice(self, patient, policy, order_lines):
        """Helper Story 8-2 : crée commande -> PEC -> facture assurance postée."""
        order = self.env['sale.order'].create({
            'partner_id': patient.id,
            'policy_id': policy.id,
            'order_line': order_lines,
        })
        order.action_create_pec()
        order.action_confirm()
        pec = order.pec_id
        pec.action_submit()
        pec.with_user(self.user_responsable).action_approve()
        pec.write({'amount_insurance_approved': order.amount_insurance or order.amount_total})
        pec.with_user(self.user_responsable).action_create_invoices()
        invoice = pec.invoice_insurance_id
        invoice.action_post()
        return invoice

    # --- Task 2.1 : Test contenu PDF format IPM (AC2, AC6) ---

    def test_pdf_content_ipm_format(self):
        """Format IPM : le HTML contient Participant, SOUS TOTAL, nom patient, produits."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        claim_sheet = self._generate_claim_sheet(wizard)
        html_str = self._render_html(claim_sheet)
        html_lower = html_str.lower()

        # Labels format IPM (case-insensitive — dynamic columns use title case)
        self.assertIn('participant', html_lower)
        self.assertIn('sous total', html_lower)
        self.assertNotIn('total general', html_lower)
        # Nom du patient (bénéficiaire et participant en format IPM)
        self.assertIn(self.patient.name, html_str)
        # Noms des produits
        self.assertIn(self.product_monture.name, html_str)
        self.assertIn(self.product_verre.name, html_str)

    # --- Task 2.2 : Test TVA inline montures format IPM (AC5, AC6) ---

    def test_pdf_tva_inline_frame_ipm(self):
        """TVA : colonne Dont TVA présente avec montant > 0 pour montures taxées."""
        # Ajouter une taxe de vente sur la monture pour générer une TVA > 0
        sale_tax = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('amount', '>', 0),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not sale_tax:
            sale_tax = self.env['account.tax'].create({
                'name': 'TVA 18%',
                'type_tax_use': 'sale',
                'amount_type': 'percent',
                'amount': 18.0,
                'company_id': self.env.company.id,
                'country_id': self.env.company.country_id.id or self.env['res.country'].search([], limit=1).id,
            })
        # Creer une nouvelle commande avec taxe sur la monture seulement
        product_monture_taxed = self.env['product.product'].create({
            'name': 'Monture Taxee TVA',
            'type': 'consu',
            'list_price': 45000.0,
            'taxes_id': [Command.set([sale_tax.id])],
        })
        product_monture_taxed.product_tmpl_id.optical_type = 'frame'

        product_verre_notax = self.env['product.product'].create({
            'name': 'Verre Sans TVA',
            'type': 'consu',
            'list_price': 30000.0,
            'taxes_id': [],
        })
        product_verre_notax.product_tmpl_id.optical_type = 'lens'

        # Creer un nouveau patient et workflow PEC pour ce test
        patient_tva = self.env['res.partner'].create({
            'name': 'Patient TVA Test',
            'is_patient': True,
        })
        policy_tva = self.env['optical.policy'].create({
            'patient_id': patient_tva.id,
            'insurer_id': self.insurer.id,
            'coverage_rate': 80.0,
            'plan_id': self.plan.id,
            'subscriber_id': self.subscriber.id,
            'beneficiary_relationship': 'holder',
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',
        })
        invoice_tva = self._create_posted_invoice(patient_tva, policy_tva, [
            Command.create({
                'product_id': product_monture_taxed.id,
                'product_uom_qty': 1,
                'price_unit': 45000.0,
            }),
            Command.create({
                'product_id': product_verre_notax.id,
                'product_uom_qty': 1,
                'price_unit': 30000.0,
                'eye_side': 'od',  # Story 19-5 : requis pour un verre
            }),
        ])

        # Vérifier que la monture a bien une TVA > 0 sur la facture
        monture_line = invoice_tva.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product' and l.product_id.optical_type == 'frame'
        )
        self.assertTrue(monture_line, "Ligne monture taxée doit exister")
        self.assertNotEqual(
            monture_line.price_total, monture_line.price_subtotal,
            "La monture taxée doit avoir price_total != price_subtotal"
        )

        # Vérifier qu'une ligne verre n'a pas de TVA
        verre_line = invoice_tva.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product' and l.product_id.optical_type == 'lens'
        )
        self.assertTrue(verre_line, "Ligne verre doit exister")
        self.assertEqual(
            verre_line.price_total, verre_line.price_subtotal,
            "Le verre sans taxe doit avoir price_total == price_subtotal"
        )

        # Créer un wizard avec cette facture seulement
        inv_d = invoice_tva.invoice_date
        wizard = self.env['optical.claim.sheet.wizard'].create({
            'insurer_id': self.insurer.id,
            'date_from': inv_d.replace(day=1),
            'date_to': (inv_d.replace(day=1) + relativedelta(months=1)) - timedelta(days=1),
        })
        wizard.action_search_invoices()
        # S'assurer que la facture taxée est dans le wizard
        self.assertIn(invoice_tva, wizard.invoice_ids)

        # Générer le bordereau persistant puis rendre le HTML
        wizard.action_generate()
        claim_sheet = invoice_tva.claim_sheet_id
        html_str = self._render_html(claim_sheet)
        html_lower = html_str.lower()
        # Mention "Dont TVA" inline supprimée du tableau — TVA exposée uniquement
        # via la ventilation fiscale en bas de document
        self.assertNotIn('dont tva', html_lower)
        # La ventilation fiscale doit montrer un montant TVA > 0
        summary = claim_sheet._get_tax_summary()
        self.assertTrue(summary['taxes'], "Il doit y avoir au moins une taxe")
        total_tax = sum(t['tax_amount'] for t in summary['taxes'])
        self.assertGreater(total_tax, 0,
                           "La TVA doit être > 0 pour les montures taxées")

    # --- Task 3.1 : Test contenu PDF format Assurance (AC1, AC6) ---

    def test_pdf_content_insurance_format(self):
        """Format Assurance : le HTML contient Souscripteur, SOUS TOTAL, nom souscripteur."""
        self.insurer.insurer_type = 'insurance'
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        claim_sheet = self._generate_claim_sheet(wizard)
        html_str = self._render_html(claim_sheet)
        html_lower = html_str.lower()

        # Labels format Assurance (case-insensitive — dynamic columns use title case)
        self.assertIn('souscripteur', html_lower)
        self.assertIn('sous total', html_lower)
        self.assertNotIn('total general', html_lower)
        # Nom du souscripteur
        self.assertIn(self.subscriber.name, html_str)

    # --- Task 3.2 : Test rendu PDF format Assurance sans erreur (AC1, AC6) ---

    def test_render_pdf_insurance_format(self):
        """Le template QWeb du bordereau format Assurance se rend en PDF sans erreur."""
        self.insurer.insurer_type = 'insurance'
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        claim_sheet = self._generate_claim_sheet(wizard)
        report = self.env.ref('optical.action_report_claim_sheet')
        content, content_type = report._render_qweb_pdf(report.id, claim_sheet.ids)
        self.assertTrue(content, "Le rendu PDF format Assurance ne doit pas être vide")

    # --- Task 4.1 : Test multi-clients dans un bordereau (AC4, AC6) ---

    def test_multiple_groups_in_bordereau(self):
        """Multi-clients IPM : 2 patients, 2 groupes distincts avec sous-totaux corrects."""
        # Créer un 2e patient avec sa propre PEC/facture
        patient2 = self.env['res.partner'].create({
            'name': 'Patient Deux Test',
            'is_patient': True,
        })
        policy2 = self.env['optical.policy'].create({
            'patient_id': patient2.id,
            'insurer_id': self.insurer.id,
            'coverage_rate': 80.0,
            'plan_id': self.plan.id,
            'subscriber_id': self.subscriber.id,
            'beneficiary_relationship': 'holder',
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',
        })
        invoice2 = self._create_posted_invoice(patient2, policy2, [
            Command.create({
                'product_id': self.product_monture.id,
                'product_uom_qty': 1,
                'price_unit': 50000.0,
            }),
            Command.create({
                'product_id': self.product_verre.id,
                'product_uom_qty': 1,
                'price_unit': 30000.0,
                'eye_side': 'od',  # Story 19-5 : requis pour un verre
            }),
        ])

        # H3 fix : wizard via helper (repose sur rollback transactionnel de TransactionCase)
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        self.assertIn(self.invoice_insurance, wizard.invoice_ids)
        self.assertIn(invoice2, wizard.invoice_ids)

        # Générer le bordereau puis vérifier le regroupement
        claim_sheet = self._generate_claim_sheet(wizard)
        groups = claim_sheet._get_invoices_grouped()
        self.assertEqual(len(groups), 2, "Doit y avoir 2 groupes (un par patient)")

        # Task 4.2 : Vérifier que la somme des sous-totaux == grand total
        grand_total = sum(g['subtotal'] for g in groups)
        expected_total = sum(inv.amount_total_signed for inv in claim_sheet.invoice_ids)
        self.assertAlmostEqual(
            grand_total, expected_total, places=2,
            msg="La somme des sous-totaux doit être égale au total général"
        )

        # Vérifier que les deux patients sont présents dans le HTML
        html_str = self._render_html(claim_sheet)
        self.assertIn(self.patient.name, html_str)
        self.assertIn(patient2.name, html_str)

    # --- Task 5.1 : Test edge case souscripteur manquant (AC6) ---

    def test_insurance_format_missing_subscriber(self):
        """Format Assurance sans souscripteur : fallback sur le patient dans le regroupement."""
        self.insurer.insurer_type = 'insurance'
        # Créer une police SANS souscripteur
        patient_no_sub = self.env['res.partner'].create({
            'name': 'Patient Sans Souscripteur',
            'is_patient': True,
        })
        policy_no_sub = self.env['optical.policy'].create({
            'patient_id': patient_no_sub.id,
            'insurer_id': self.insurer.id,
            'coverage_rate': 80.0,
            'plan_id': self.plan.id,
            'subscriber_id': False,
            'beneficiary_relationship': 'holder',
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',
        })
        invoice_no_sub = self._create_posted_invoice(patient_no_sub, policy_no_sub, [
            Command.create({
                'product_id': self.product_verre.id,
                'product_uom_qty': 1,
                'price_unit': 25000.0,
                'eye_side': 'od',  # Story 19-5 : requis pour un verre
            }),
        ])

        # Wizard format Assurance (même mois que le setup — rollback transactionnel)
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        self.assertIn(invoice_no_sub, wizard.invoice_ids)

        # Générer le bordereau puis vérifier le fallback dans _get_invoices_grouped
        claim_sheet = self._generate_claim_sheet(wizard)
        groups = claim_sheet._get_invoices_grouped()
        # Trouver le groupe correspondant à la facture sans souscripteur
        no_sub_group = None
        for group in groups:
            if invoice_no_sub in group['invoices']:
                no_sub_group = group
                break
        self.assertIsNotNone(no_sub_group, "Le groupe de la facture sans souscripteur doit exister")
        # Fallback : group_label = patient name quand subscriber est absent
        self.assertEqual(
            no_sub_group['group_label'], patient_no_sub.name,
            "En format Assurance sans souscripteur, le group_label doit être le nom du patient (fallback)"
        )

        # Le HTML doit se rendre sans erreur avec les bons labels format Assurance
        html_str = self._render_html(claim_sheet)
        html_lower = html_str.lower()
        self.assertIn('sous total', html_lower)
        self.assertIn(patient_no_sub.name, html_str)
        # L2 fix : vérifier que la colonne Souscripteur est présente (format Assurance)
        self.assertIn('souscripteur', html_lower)

    # --- Review fix M3 : Test multi-souscripteurs format Assurance (AC4, AC6) ---

    def test_multiple_subscribers_insurance_format(self):
        """Format Assurance multi-souscripteurs : 2 souscripteurs, 2 groupes distincts."""
        self.insurer.insurer_type = 'insurance'
        # Créer un 2e souscripteur avec son patient et sa police
        subscriber2 = self.env['res.partner'].create({
            'name': 'Souscripteur Deux SA',
            'is_company': True,
        })
        patient2 = self.env['res.partner'].create({
            'name': 'Patient Souscripteur Deux',
            'is_patient': True,
        })
        policy2 = self.env['optical.policy'].create({
            'patient_id': patient2.id,
            'insurer_id': self.insurer.id,
            'coverage_rate': 80.0,
            'plan_id': self.plan.id,
            'subscriber_id': subscriber2.id,
            'beneficiary_relationship': 'holder',
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',
        })
        invoice2 = self._create_posted_invoice(patient2, policy2, [
            Command.create({
                'product_id': self.product_monture.id,
                'product_uom_qty': 1,
                'price_unit': 40000.0,
            }),
        ])

        # Wizard format Assurance avec les 2 factures (2 souscripteurs)
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        self.assertIn(self.invoice_insurance, wizard.invoice_ids)
        self.assertIn(invoice2, wizard.invoice_ids)

        # Générer le bordereau puis vérifier le regroupement par souscripteur
        claim_sheet = self._generate_claim_sheet(wizard)
        groups = claim_sheet._get_invoices_grouped()
        self.assertEqual(len(groups), 2, "Doit y avoir 2 groupes (un par souscripteur)")

        # Vérifier que la somme des sous-totaux == grand total
        grand_total = sum(g['subtotal'] for g in groups)
        expected_total = sum(inv.amount_total_signed for inv in claim_sheet.invoice_ids)
        self.assertAlmostEqual(
            grand_total, expected_total, places=2,
            msg="La somme des sous-totaux doit être égale au total général"
        )

        # Vérifier que les deux souscripteurs sont présents dans le HTML
        html_str = self._render_html(claim_sheet)
        html_lower = html_str.lower()
        self.assertIn(self.subscriber.name, html_str)
        self.assertIn(subscriber2.name, html_str)
        self.assertIn('souscripteur', html_lower)
        self.assertIn('sous total', html_lower)

    # ================================================================
    # Story 8-3 : Tests bordereau persistant, reference, paiement
    # ================================================================

    # --- Task 7.1 : Test génération crée un claim_sheet ---

    def test_generate_creates_claim_sheet(self):
        """Le wizard génère un optical.claim.sheet avec la bonne référence, assureur, mois, année, factures liées."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        wizard.action_generate()
        claim_sheet = self.invoice_insurance.claim_sheet_id
        self.assertTrue(claim_sheet, "Un claim_sheet doit être créé")
        self.assertTrue(claim_sheet.name.startswith('BRD/'), "La référence doit commencer par BRD/")
        self.assertEqual(claim_sheet.insurer_id, self.insurer)
        inv_date = self.invoice_insurance.invoice_date
        self.assertEqual(claim_sheet.date_from, inv_date.replace(day=1))
        self.assertEqual(
            claim_sheet.date_to,
            (inv_date.replace(day=1) + relativedelta(months=1)) - timedelta(days=1),
        )
        self.assertIn(self.invoice_insurance, claim_sheet.invoice_ids)

    # --- Task 7.2 : Test références séquentielles ---

    def test_claim_sheet_reference_sequential(self):
        """2 générations produisent des références différentes et séquentielles."""
        # 1ère génération
        wizard1 = self._create_wizard()
        wizard1.action_search_invoices()
        wizard1.action_generate()
        sheet1 = self.invoice_insurance.claim_sheet_id

        # Annuler le premier bordereau pour libérer la contrainte d'unicité
        sheet1.with_user(self.user_responsable).action_cancel()

        # 2e génération (les factures sont libérées par action_cancel)
        wizard2 = self._create_wizard()
        wizard2.action_search_invoices()
        wizard2.action_generate()
        sheet2 = self.invoice_insurance.claim_sheet_id

        self.assertNotEqual(sheet1.name, sheet2.name, "Les références doivent être différentes")
        self.assertTrue(sheet1.name.startswith('BRD/'))
        self.assertTrue(sheet2.name.startswith('BRD/'))

    # --- Task 7.3 : Test référence dans le PDF ---

    def test_claim_sheet_reference_in_pdf(self):
        """La référence du bordereau apparaît dans le HTML rendu."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        claim_sheet = self._generate_claim_sheet(wizard)
        html_str = self._render_html(claim_sheet)
        self.assertIn(claim_sheet.name, html_str,
                       "La référence du bordereau doit apparaître dans le HTML")

    # --- Task 7.4 : Test amount_total computed ---

    def test_claim_sheet_amount_total(self):
        """Le computed amount_total est égal à la somme des factures."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        claim_sheet = self._generate_claim_sheet(wizard)
        expected = sum(claim_sheet.invoice_ids.mapped('amount_total_signed'))
        self.assertAlmostEqual(
            claim_sheet.amount_total, expected, places=2,
            msg="amount_total doit être la somme des amount_total_signed des factures"
        )

    # --- Task 7.5 : Test payment computed ---

    def test_claim_sheet_payment_computed(self):
        """is_fully_paid passe a True quand les factures sont payées."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        claim_sheet = self._generate_claim_sheet(wizard)
        # Avant paiement
        self.assertFalse(claim_sheet.is_fully_paid)
        self.assertGreater(claim_sheet.amount_residual, 0)

        # Configurer le journal bancaire pour paiement direct (pas in_payment)
        bank_journal = self.env['account.journal'].search(
            [('type', '=', 'bank'), ('company_id', '=', self.env.company.id)], limit=1
        )
        # Pointer le outstanding account vers le compte bancaire lui-même
        # → le paiement est directement marqué 'paid' sans rapprochement
        for method_line in bank_journal.inbound_payment_method_line_ids:
            method_line.payment_account_id = bank_journal.default_account_id

        # Payer les factures via le wizard natif Odoo
        for invoice in claim_sheet.invoice_ids:
            ctx = {'active_model': 'account.move', 'active_ids': invoice.ids}
            payment_wizard = self.env['account.payment.register'].with_context(**ctx).create({
                'journal_id': bank_journal.id,
            })
            payment_wizard._create_payments()

        # Invalider le cache pour forcer le recalcul des computed
        claim_sheet.invalidate_recordset()

        # Après paiement
        for invoice in claim_sheet.invoice_ids:
            self.assertEqual(invoice.payment_state, 'paid',
                             "La facture doit être en statut paid")
        self.assertTrue(claim_sheet.is_fully_paid,
                        "is_fully_paid doit être True après paiement complet")
        self.assertAlmostEqual(claim_sheet.amount_residual, 0, places=2)

    # --- Task 7.6 : Test unmark efface claim_sheet_id ---

    def test_unmark_clears_claim_sheet_id(self):
        """action_unmark_insurance_sent efface claim_sheet_id sur les factures."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        wizard.action_generate()
        self.assertTrue(self.invoice_insurance.claim_sheet_id)
        # Annuler le marquage
        self.invoice_insurance.with_user(self.user_responsable).action_unmark_insurance_sent()
        self.assertFalse(self.invoice_insurance.claim_sheet_id,
                         "claim_sheet_id doit être vide après unmark")
        self.assertFalse(self.invoice_insurance.insurance_sent)

    # --- Task 7.7 : Test suppression interdite ---

    def test_claim_sheet_no_delete(self):
        """Tenter de supprimer un bordereau lève UserError."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        claim_sheet = self._generate_claim_sheet(wizard)
        with self.assertRaises(UserError):
            claim_sheet.unlink()

    # --- Task 7.8 : Test modification interdite ---

    def test_claim_sheet_no_modify(self):
        """Tenter de modifier les champs protégés lève UserError."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        claim_sheet = self._generate_claim_sheet(wizard)
        with self.assertRaises(UserError):
            claim_sheet.write({'insurer_id': self.insurer.id})
        with self.assertRaises(UserError):
            claim_sheet.write({'date_from': date(2025, 1, 1)})
        with self.assertRaises(UserError):
            claim_sheet.write({'date_to': date(2025, 1, 31)})

    # --- Task 8-6 : Test contrainte dates wizard ---

    def test_wizard_date_constraint_invalid(self):
        """Créer un wizard avec date_to < date_from lève ValidationError."""
        from odoo.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.env['optical.claim.sheet.wizard'].with_user(
                self.user_responsable
            ).create({
                'insurer_id': self.insurer.id,
                'date_from': date(2026, 3, 15),
                'date_to': date(2026, 3, 1),
            })

    def test_wizard_date_constraint_equal_ok(self):
        """Créer un wizard avec date_from == date_to ne lève pas d'erreur."""
        wizard = self.env['optical.claim.sheet.wizard'].with_user(
            self.user_responsable
        ).create({
            'insurer_id': self.insurer.id,
            'date_from': date(2026, 3, 15),
            'date_to': date(2026, 3, 15),
        })
        self.assertEqual(wizard.date_from, wizard.date_to)

    # ================================================================
    # Story 8-5 : Tests ventilation fiscale, total en lettres, mention legale
    # ================================================================

    def test_tax_summary_mixed_lines(self):
        """_get_tax_summary avec lignes exonérées (verres) et taxées (montures)."""
        # Créer une taxe de vente
        sale_tax = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('amount', '>', 0),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not sale_tax:
            sale_tax = self.env['account.tax'].create({
                'name': 'TVA 18% Fiscal Test',
                'type_tax_use': 'sale',
                'amount_type': 'percent',
                'amount': 18.0,
                'company_id': self.env.company.id,
                'country_id': self.env.company.country_id.id or self.env['res.country'].search([], limit=1).id,
            })
        # Monture avec taxe
        product_taxed = self.env['product.product'].create({
            'name': 'Monture Fiscal Test',
            'type': 'consu',
            'list_price': 100000.0,
            'taxes_id': [Command.set([sale_tax.id])],
        })
        product_taxed.product_tmpl_id.optical_type = 'frame'
        # Verre sans taxe
        product_exempt = self.env['product.product'].create({
            'name': 'Verre Fiscal Test',
            'type': 'consu',
            'list_price': 125000.0,
            'taxes_id': [],
        })
        product_exempt.product_tmpl_id.optical_type = 'lens'

        patient_fiscal = self.env['res.partner'].create({
            'name': 'Patient Fiscal', 'is_patient': True,
        })
        policy_fiscal = self.env['optical.policy'].create({
            'patient_id': patient_fiscal.id,
            'insurer_id': self.insurer.id,
            'coverage_rate': 80.0,
            'plan_id': self.plan.id,
            'subscriber_id': self.subscriber.id,
            'beneficiary_relationship': 'holder',
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',
        })
        invoice = self._create_posted_invoice(patient_fiscal, policy_fiscal, [
            Command.create({
                'product_id': product_taxed.id,
                'product_uom_qty': 1,
                'price_unit': 100000.0,
            }),
            Command.create({
                'product_id': product_exempt.id,
                'product_uom_qty': 1,
                'price_unit': 125000.0,
                'eye_side': 'od',  # Story 19-5 : requis pour un verre
            }),
        ])

        wizard = self.env['optical.claim.sheet.wizard'].create({
            'insurer_id': self.insurer.id,
            'date_from': invoice.invoice_date.replace(day=1),
            'date_to': (invoice.invoice_date.replace(day=1) + relativedelta(months=1)) - timedelta(days=1),
        })
        wizard.action_search_invoices()
        wizard.action_generate()
        claim_sheet = invoice.claim_sheet_id

        summary = claim_sheet._get_tax_summary()
        # Verre 125000 exonéré
        self.assertGreater(summary['exempt_amount'], 0,
                           "Le montant exonéré doit être > 0 (verres)")
        # Au moins une taxe dynamique
        self.assertTrue(summary['taxes'], "Il doit y avoir au moins une taxe")
        tax_line = summary['taxes'][0]
        self.assertGreater(tax_line['base'], 0, "Le montant HT taxé doit être > 0")
        self.assertGreater(tax_line['tax_amount'], 0, "Le montant TVA doit être > 0")
        self.assertTrue(tax_line['name'], "Le nom de la taxe doit être renseigné")
        # Total = exempt + sum(base + tax_amount)
        expected = summary['exempt_amount'] + sum(
            t['base'] + t['tax_amount'] for t in summary['taxes']
        )
        self.assertAlmostEqual(summary['amount_total'], expected, places=2)

    def test_tax_summary_exempt_only(self):
        """_get_tax_summary avec uniquement des lignes exonérées."""
        # Les produits du setup commun n'ont pas de taxe par défaut
        product_no_tax = self.env['product.product'].create({
            'name': 'Verre Exempt Only', 'type': 'consu',
            'list_price': 50000.0, 'taxes_id': [],
        })
        patient_ex = self.env['res.partner'].create({
            'name': 'Patient Exempt Only', 'is_patient': True,
        })
        policy_ex = self.env['optical.policy'].create({
            'patient_id': patient_ex.id,
            'insurer_id': self.insurer.id,
            'coverage_rate': 80.0,
            'plan_id': self.plan.id,
            'subscriber_id': self.subscriber.id,
            'beneficiary_relationship': 'holder',
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',
        })
        invoice = self._create_posted_invoice(patient_ex, policy_ex, [
            Command.create({
                'product_id': product_no_tax.id,
                'product_uom_qty': 1,
                'price_unit': 50000.0,
            }),
        ])
        wizard = self.env['optical.claim.sheet.wizard'].create({
            'insurer_id': self.insurer.id,
            'date_from': invoice.invoice_date.replace(day=1),
            'date_to': (invoice.invoice_date.replace(day=1) + relativedelta(months=1)) - timedelta(days=1),
        })
        wizard.action_search_invoices()
        wizard.action_generate()
        claim_sheet = invoice.claim_sheet_id

        summary = claim_sheet._get_tax_summary()
        self.assertGreater(summary['exempt_amount'], 0)
        self.assertEqual(len(summary['taxes']), 0,
                         "Aucune taxe ne doit apparaître (tout exonéré)")

    def test_tax_summary_taxed_only(self):
        """_get_tax_summary avec uniquement des lignes taxées."""
        sale_tax = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('amount', '>', 0),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not sale_tax:
            sale_tax = self.env['account.tax'].create({
                'name': 'TVA 18% Taxed Only',
                'type_tax_use': 'sale',
                'amount_type': 'percent',
                'amount': 18.0,
                'company_id': self.env.company.id,
                'country_id': self.env.company.country_id.id or self.env['res.country'].search([], limit=1).id,
            })
        product_taxed = self.env['product.product'].create({
            'name': 'Monture Taxed Only', 'type': 'consu',
            'list_price': 80000.0,
            'taxes_id': [Command.set([sale_tax.id])],
        })
        # Assureur isolé pour ne pas capter les factures du setup commun
        insurer_iso = self.env['res.partner'].create({
            'name': 'IPM Taxed Only Iso',
            'is_insurer': True,
            'insurer_type': 'ipm',
        })
        patient_tx = self.env['res.partner'].create({
            'name': 'Patient Taxed Only', 'is_patient': True,
        })
        policy_tx = self.env['optical.policy'].create({
            'patient_id': patient_tx.id,
            'insurer_id': insurer_iso.id,
            'coverage_rate': 80.0,
            'plan_id': self.plan.id,
            'subscriber_id': self.subscriber.id,
            'beneficiary_relationship': 'holder',
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',
        })
        invoice = self._create_posted_invoice(patient_tx, policy_tx, [
            Command.create({
                'product_id': product_taxed.id,
                'product_uom_qty': 1,
                'price_unit': 80000.0,
            }),
        ])
        wizard = self.env['optical.claim.sheet.wizard'].create({
            'insurer_id': insurer_iso.id,
            'date_from': invoice.invoice_date.replace(day=1),
            'date_to': (invoice.invoice_date.replace(day=1) + relativedelta(months=1)) - timedelta(days=1),
        })
        wizard.action_search_invoices()
        wizard.action_generate()
        claim_sheet = invoice.claim_sheet_id

        summary = claim_sheet._get_tax_summary()
        self.assertAlmostEqual(summary['exempt_amount'], 0, places=2)
        self.assertTrue(summary['taxes'], "Il doit y avoir au moins une taxe")
        self.assertGreater(summary['taxes'][0]['base'], 0)
        self.assertGreater(summary['taxes'][0]['tax_amount'], 0)
        # Le nom de la taxe doit être dynamique (pas en dur)
        self.assertTrue(summary['taxes'][0]['name'])

    def test_amount_to_text(self):
        """amount_to_text retourne le montant en lettres français majuscules + FRANCS CFA."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        claim_sheet = self._generate_claim_sheet(wizard)
        text = claim_sheet.amount_to_text()
        self.assertTrue(text.isupper(), "Le texte doit être en majuscules")
        self.assertTrue(text.endswith('FRANCS CFA'),
                        "Le texte doit se terminer par FRANCS CFA")
        # Doit contenir au moins un mot (pas vide)
        self.assertGreater(len(text), len('FRANCS CFA'))

    def test_fiscal_section_in_html(self):
        """Le HTML du bordereau contient la ventilation fiscale et le total en lettres."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        claim_sheet = self._generate_claim_sheet(wizard)
        html_str = self._render_html(claim_sheet)
        # Les factures du setup commun sont sans taxe → lignes exonérées
        # Labels ventilation
        self.assertIn('MONTANT EXONORÉ', html_str)
        # Total en lettres (FRANCS CFA)
        self.assertIn('FRANCS CFA', html_str)

    def test_legal_note_from_tax_invoice_legal_notes(self):
        """La mention légale vient de invoice_legal_notes de la taxe 0%."""
        # Créer une taxe 0% avec mention légale
        tax_exempt = self.env['account.tax'].create({
            'name': 'Exoneration TVA',
            'type_tax_use': 'sale',
            'amount_type': 'percent',
            'amount': 0.0,
            'company_id': self.env.company.id,
            'invoice_legal_notes': "Exonération de TVA conformément à l'article 361-2 du CGI",
            'country_id': self.env.company.country_id.id or self.env['res.country'].search([], limit=1).id,
        })
        # Produit avec taxe 0%
        product_exempt = self.env['product.product'].create({
            'name': 'Verre LegalNote', 'type': 'consu',
            'list_price': 50000.0,
            'taxes_id': [Command.set([tax_exempt.id])],
        })
        insurer_ln = self.env['res.partner'].create({
            'name': 'IPM LegalNote Iso', 'is_insurer': True, 'insurer_type': 'ipm',
        })
        patient_ln = self.env['res.partner'].create({
            'name': 'Patient LegalNote', 'is_patient': True,
        })
        policy_ln = self.env['optical.policy'].create({
            'patient_id': patient_ln.id,
            'insurer_id': insurer_ln.id,
            'coverage_rate': 80.0,
            'plan_id': self.plan.id,
            'subscriber_id': self.subscriber.id,
            'beneficiary_relationship': 'holder',
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',
        })
        invoice = self._create_posted_invoice(patient_ln, policy_ln, [
            Command.create({
                'product_id': product_exempt.id,
                'product_uom_qty': 1,
                'price_unit': 50000.0,
            }),
        ])
        wizard = self.env['optical.claim.sheet.wizard'].create({
            'insurer_id': insurer_ln.id,
            'date_from': invoice.invoice_date.replace(day=1),
            'date_to': (invoice.invoice_date.replace(day=1) + relativedelta(months=1)) - timedelta(days=1),
        })
        wizard.action_search_invoices()
        wizard.action_generate()
        claim_sheet = invoice.claim_sheet_id
        html_str = self._render_html(claim_sheet)
        # La mention légale de la taxe 0% doit apparaître
        self.assertIn("article 361-2", html_str)
        # Ligne traitée comme exonérée (taxe 0%)
        self.assertIn('MONTANT EXONORÉ', html_str)

    def test_no_legal_notes_no_mention(self):
        """Sans invoice_legal_notes sur les taxes, aucune mention légale n'apparaît."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        claim_sheet = self._generate_claim_sheet(wizard)
        html_str = self._render_html(claim_sheet)
        # Pas de mention légale (produits du setup commun sans invoice_legal_notes)
        self.assertNotIn("article 361-2", html_str)
        # Mais la ventilation et le total en lettres sont présents
        self.assertIn('MONTANT EXONORÉ', html_str)
        self.assertIn('FRANCS CFA', html_str)

    def test_fiscal_section_no_exempt_no_exonore_label(self):
        """Sans lignes exonérées, MONTANT EXONORÉ n'apparaît pas."""
        sale_tax = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('amount', '>', 0),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not sale_tax:
            sale_tax = self.env['account.tax'].create({
                'name': 'TVA 18% NoExempt',
                'type_tax_use': 'sale',
                'amount_type': 'percent',
                'amount': 18.0,
                'company_id': self.env.company.id,
                'country_id': self.env.company.country_id.id or self.env['res.country'].search([], limit=1).id,
            })
        product_taxed = self.env['product.product'].create({
            'name': 'Monture NoExempt', 'type': 'consu',
            'list_price': 60000.0,
            'taxes_id': [Command.set([sale_tax.id])],
        })
        insurer_ne = self.env['res.partner'].create({
            'name': 'IPM NoExempt Iso', 'is_insurer': True, 'insurer_type': 'ipm',
        })
        patient_ne = self.env['res.partner'].create({
            'name': 'Patient NoExempt', 'is_patient': True,
        })
        policy_ne = self.env['optical.policy'].create({
            'patient_id': patient_ne.id,
            'insurer_id': insurer_ne.id,
            'coverage_rate': 80.0,
            'plan_id': self.plan.id,
            'subscriber_id': self.subscriber.id,
            'beneficiary_relationship': 'holder',
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',
        })
        invoice = self._create_posted_invoice(patient_ne, policy_ne, [
            Command.create({
                'product_id': product_taxed.id,
                'product_uom_qty': 1,
                'price_unit': 60000.0,
            }),
        ])
        wizard = self.env['optical.claim.sheet.wizard'].create({
            'insurer_id': insurer_ne.id,
            'date_from': invoice.invoice_date.replace(day=1),
            'date_to': (invoice.invoice_date.replace(day=1) + relativedelta(months=1)) - timedelta(days=1),
        })
        wizard.action_search_invoices()
        wizard.action_generate()
        claim_sheet = invoice.claim_sheet_id
        html_str = self._render_html(claim_sheet)
        # Pas de MONTANT EXONORÉ (aucune ligne exonérée)
        self.assertNotIn('MONTANT EXONORÉ', html_str)
        # Mais MONTANT HT + label taxe dynamique sont présents
        self.assertIn('MONTANT HT', html_str)
        self.assertIn(sale_tax.name, html_str)
        # Total en lettres toujours présent
        self.assertIn('FRANCS CFA', html_str)

    def test_amount_to_text_zero(self):
        """amount_to_text retourne ZERO FRANC CFA pour un montant nul."""
        sheet = self.env['optical.claim.sheet'].create({
            'insurer_id': self.insurer.id,
            'date_from': date(2026, 3, 1),
            'date_to': date(2026, 3, 31),
        })
        self.assertAlmostEqual(sheet.amount_total, 0, places=2)
        self.assertEqual(sheet.amount_to_text(), "ZERO FRANC CFA")

    def test_tax_summary_exempt_with_zero_tax(self):
        """Lignes avec taxe 0% sont traitées comme exonérées dans _get_tax_summary."""
        tax_zero = self.env['account.tax'].create({
            'name': 'Exoneration TVA ZeroTest',
            'type_tax_use': 'sale',
            'amount_type': 'percent',
            'amount': 0.0,
            'company_id': self.env.company.id,
            'country_id': self.env.company.country_id.id or self.env['res.country'].search([], limit=1).id,
        })
        product_zero = self.env['product.product'].create({
            'name': 'Verre ZeroTax', 'type': 'consu',
            'list_price': 40000.0,
            'taxes_id': [Command.set([tax_zero.id])],
        })
        insurer_zt = self.env['res.partner'].create({
            'name': 'IPM ZeroTax Iso', 'is_insurer': True, 'insurer_type': 'ipm',
        })
        patient_zt = self.env['res.partner'].create({
            'name': 'Patient ZeroTax', 'is_patient': True,
        })
        policy_zt = self.env['optical.policy'].create({
            'patient_id': patient_zt.id,
            'insurer_id': insurer_zt.id,
            'coverage_rate': 80.0,
            'plan_id': self.plan.id,
            'subscriber_id': self.subscriber.id,
            'beneficiary_relationship': 'holder',
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',
        })
        invoice = self._create_posted_invoice(patient_zt, policy_zt, [
            Command.create({
                'product_id': product_zero.id,
                'product_uom_qty': 1,
                'price_unit': 40000.0,
            }),
        ])
        wizard = self.env['optical.claim.sheet.wizard'].create({
            'insurer_id': insurer_zt.id,
            'date_from': invoice.invoice_date.replace(day=1),
            'date_to': (invoice.invoice_date.replace(day=1) + relativedelta(months=1)) - timedelta(days=1),
        })
        wizard.action_search_invoices()
        wizard.action_generate()
        claim_sheet = invoice.claim_sheet_id
        summary = claim_sheet._get_tax_summary()
        # Ligne avec taxe 0% comptée comme exonérée
        self.assertGreater(summary['exempt_amount'], 0,
                           "Taxe 0% doit être traitée comme exonérée")
        self.assertEqual(len(summary['taxes']), 0,
                         "Aucune taxe non-nulle ne doit apparaître")
        # MONTANT EXONORÉ visible dans le HTML
        html_str = self._render_html(claim_sheet)
        self.assertIn('MONTANT EXONORÉ', html_str)

    # ============================================================
    # Story 8-7 : Type bordereau, contrainte unicité, parent_id
    # ============================================================

    @mute_logger('odoo.sql_db')
    def test_unique_constraint_duplicate_normal(self):
        """AC1 — Deux bordereaux normal meme assureur+periode+state=generated → erreur SQL."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        wizard.action_generate()
        # Créer un deuxième bordereau directement (bypass verification Python)
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.env['optical.claim.sheet'].create({
                'insurer_id': self.insurer.id,
                'date_from': wizard.date_from,
                'date_to': wizard.date_to,
                'type': 'normal',
            })

    def test_duplicate_check_python_before_create(self):
        """AC2 — Wizard détecte le doublon Python avant create → UserError."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        wizard.action_generate()
        # Libérer les factures pour pouvoir relancer le wizard
        self.invoice_insurance.sudo().write({
            'insurance_sent': False,
            'insurance_sent_date': False,
            'claim_sheet_id': False,
        })
        wizard2 = self._create_wizard()
        wizard2.action_search_invoices()
        with self.assertRaises(UserError):
            wizard2.action_generate()

    def test_normal_after_cancel_ok(self):
        """AC2 — Annuler puis régénérer un normal → pas de doublon."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        wizard.action_generate()
        claim_sheet = self.invoice_insurance.claim_sheet_id
        # Annuler le bordereau
        claim_sheet.with_user(self.user_responsable).action_cancel()
        # Régénérer un normal pour la même période
        wizard2 = self._create_wizard()
        wizard2.action_search_invoices()
        # Ne doit PAS lever d'erreur
        wizard2.action_generate()
        new_sheet = self.invoice_insurance.claim_sheet_id
        self.assertEqual(new_sheet.type, 'normal')
        self.assertEqual(new_sheet.state, 'generated')

    def test_complementary_with_parent(self):
        """AC3/AC4 — Type complémentaire + parent_id → génération OK."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        wizard.action_generate()
        parent_sheet = self.invoice_insurance.claim_sheet_id
        # Libérer les factures
        self.invoice_insurance.sudo().write({
            'insurance_sent': False,
            'insurance_sent_date': False,
            'claim_sheet_id': False,
        })
        wizard2 = self._create_wizard(type='complementary', parent_id=parent_sheet.id)
        wizard2.action_search_invoices()
        wizard2.action_generate()
        child_sheet = self.invoice_insurance.claim_sheet_id
        self.assertEqual(child_sheet.type, 'complementary')
        self.assertEqual(child_sheet.parent_id, parent_sheet)

    def test_rectificative_with_parent(self):
        """AC3/AC4 — Type rectificatif + parent_id → génération OK."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        wizard.action_generate()
        parent_sheet = self.invoice_insurance.claim_sheet_id
        # Libérer les factures
        self.invoice_insurance.sudo().write({
            'insurance_sent': False,
            'insurance_sent_date': False,
            'claim_sheet_id': False,
        })
        wizard2 = self._create_wizard(type='rectificative', parent_id=parent_sheet.id)
        wizard2.action_search_invoices()
        wizard2.action_generate()
        child_sheet = self.invoice_insurance.claim_sheet_id
        self.assertEqual(child_sheet.type, 'rectificative')
        self.assertEqual(child_sheet.parent_id, parent_sheet)

    def test_parent_required_if_not_normal(self):
        """AC4 — Type complémentaire sans parent → ValidationError."""
        with self.assertRaises(ValidationError):
            self._create_wizard(type='complementary')

    def test_parent_required_if_rectificative(self):
        """AC4 — Type rectificatif sans parent → ValidationError."""
        with self.assertRaises(ValidationError):
            self._create_wizard(type='rectificative')

    def test_pdf_title_normal(self):
        """AC5 — Le titre PDF d'un bordereau normal est 'BORDEREAU' sans suffixe."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        wizard.action_generate()
        claim_sheet = self.invoice_insurance.claim_sheet_id
        html_str = self._render_html(claim_sheet)
        self.assertIn('BORDEREAU', html_str)
        self.assertNotIn('COMPLEMENTAIRE', html_str)
        self.assertNotIn('RECTIFICATIF', html_str)

    def test_pdf_title_complementary(self):
        """AC5 — Le titre PDF d'un complémentaire contient 'BORDEREAU COMPLEMENTAIRE'."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        wizard.action_generate()
        parent_sheet = self.invoice_insurance.claim_sheet_id
        # Libérer les factures
        self.invoice_insurance.sudo().write({
            'insurance_sent': False,
            'insurance_sent_date': False,
            'claim_sheet_id': False,
        })
        wizard2 = self._create_wizard(type='complementary', parent_id=parent_sheet.id)
        wizard2.action_search_invoices()
        wizard2.action_generate()
        child_sheet = self.invoice_insurance.claim_sheet_id
        html_str = self._render_html(child_sheet)
        self.assertIn('BORDEREAU', html_str)
        self.assertIn('COMPLEMENTAIRE', html_str)
        self.assertIn(parent_sheet.name, html_str)

    def test_pdf_title_rectificative(self):
        """AC5 — Le titre PDF d'un rectificatif contient 'BORDEREAU RECTIFICATIF'."""
        wizard = self._create_wizard()
        wizard.action_search_invoices()
        wizard.action_generate()
        parent_sheet = self.invoice_insurance.claim_sheet_id
        # Libérer les factures
        self.invoice_insurance.sudo().write({
            'insurance_sent': False,
            'insurance_sent_date': False,
            'claim_sheet_id': False,
        })
        wizard2 = self._create_wizard(type='rectificative', parent_id=parent_sheet.id)
        wizard2.action_search_invoices()
        wizard2.action_generate()
        child_sheet = self.invoice_insurance.claim_sheet_id
        html_str = self._render_html(child_sheet)
        self.assertIn('BORDEREAU', html_str)
        self.assertIn('RECTIFICATIF', html_str)
        self.assertIn(parent_sheet.name, html_str)
