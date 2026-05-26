# -*- coding: utf-8 -*-
from odoo import Command
from odoo.tests import tagged, TransactionCase


@tagged('post_install', '-at_install')
class TestOperatingUnit(TransactionCase):
    """Tests OU pour le module bridge optical_operating_unit."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.group_optical_user = cls.env.ref('optical.group_optical_user')
        cls.group_optical_manager = cls.env.ref('optical.group_optical_manager')
        cls.group_multi_ou = cls.env.ref('operating_unit.group_multi_operating_unit')
        cls.group_all_ou = cls.env.ref('operating_unit_access_all.group_all_operating_unit')
        cls.group_manager_ou = cls.env.ref('operating_unit.group_manager_operating_unit')

        cls.ou_a = cls.env['operating.unit'].create({
            'name': 'Boutique Test A',
            'code': 'BTA',
            'partner_id': cls.env.company.partner_id.id,
            'company_id': cls.env.company.id,
        })
        cls.ou_b = cls.env['operating.unit'].create({
            'name': 'Boutique Test B',
            'code': 'BTB',
            'partner_id': cls.env.company.partner_id.id,
            'company_id': cls.env.company.id,
        })

        cls.warehouse_a = cls.env['stock.warehouse'].create({
            'name': 'Entrepot Boutique A',
            'code': 'WHA',
            'operating_unit_id': cls.ou_a.id,
            'company_id': cls.env.company.id,
        })
        cls.warehouse_b = cls.env['stock.warehouse'].create({
            'name': 'Entrepot Boutique B',
            'code': 'WHB',
            'operating_unit_id': cls.ou_b.id,
            'company_id': cls.env.company.id,
        })

        cls.user_vendeur = cls.env['res.users'].with_context(
            no_reset_password=True, tracking_disable=True,
        ).create({
            'name': 'Vendeur OU Test',
            'login': 'vendeur_ou_test',
            'email': 'vendeur_ou@test.com',
            'groups_id': [Command.set([
                cls.group_optical_user.id,
                cls.env.ref('base.group_user').id,
                cls.env.ref('sales_team.group_sale_salesman').id,
                cls.group_multi_ou.id,
            ])],
            'default_operating_unit_id': cls.ou_a.id,
            'operating_unit_ids': [(4, cls.ou_a.id)],
        })

        cls.user_directeur = cls.env['res.users'].with_context(
            no_reset_password=True, tracking_disable=True,
        ).create({
            'name': 'Directeur OU Test',
            'login': 'directeur_ou_test',
            'email': 'directeur_ou@test.com',
            'groups_id': [Command.set([
                cls.group_optical_manager.id,
                cls.env.ref('base.group_user').id,
                cls.env.ref('sales_team.group_sale_salesman').id,
                cls.env.ref('sales_team.group_sale_salesman_all_leads').id,
                cls.env.ref('account.group_account_invoice').id,
                cls.group_multi_ou.id,
                cls.group_manager_ou.id,
                cls.group_all_ou.id,
            ])],
            'default_operating_unit_id': cls.ou_a.id,
            'operating_unit_ids': [(4, cls.ou_a.id), (4, cls.ou_b.id)],
        })

        cls.partner = cls.env['res.partner'].create({'name': 'Client OU Test'})
        cls.product = cls.env['product.product'].create({
            'name': 'Produit OU Test',
            'type': 'consu',
            'list_price': 100.0,
        })

        cls.so_ou_a = cls.env['sale.order'].create({
            'partner_id': cls.partner.id,
            'operating_unit_id': cls.ou_a.id,
            'warehouse_id': cls.warehouse_a.id,
            'team_id': False,
            'user_id': cls.user_vendeur.id,
            'order_line': [Command.create({
                'product_id': cls.product.id,
                'product_uom_qty': 1,
                'price_unit': 100.0,
            })],
        })

        cls.so_ou_b = cls.env['sale.order'].create({
            'partner_id': cls.partner.id,
            'operating_unit_id': cls.ou_b.id,
            'warehouse_id': cls.warehouse_b.id,
            'team_id': False,
            'user_id': cls.user_directeur.id,
            'order_line': [Command.create({
                'product_id': cls.product.id,
                'product_uom_qty': 1,
                'price_unit': 200.0,
            })],
        })

    # === AC #1 : Menu OU accessible ===

    def test_menu_ou_accessible_responsable(self):
        """Le responsable optique voit le menu Configuration > Unites operationnelles."""
        menu = self.env.ref('optical_operating_unit.menu_optical_config_ou')
        self.assertTrue(menu)
        self.assertIn(
            self.group_optical_manager,
            menu.groups_id,
        )

    def test_menu_ou_action_points_to_oca(self):
        """Le menu OU pointe vers l'action OCA de gestion des OU."""
        menu = self.env.ref('optical_operating_unit.menu_optical_config_ou')
        action = self.env.ref('operating_unit.action_operating_unit_tree')
        self.assertEqual(menu.action, action)

    # === AC #2 : Default OU ===

    def test_default_ou_vendeur(self):
        """_get_default_operating_unit() retourne l'OU A pour le vendeur."""
        default_ou = self.env['res.users'].with_user(
            self.user_vendeur
        )._get_default_operating_unit()
        self.assertEqual(default_ou, self.ou_a)

    def test_default_ou_directeur(self):
        """_get_default_operating_unit() retourne l'OU A pour le directeur."""
        default_ou = self.env['res.users'].with_user(
            self.user_directeur
        )._get_default_operating_unit()
        self.assertEqual(default_ou, self.ou_a)

    # === AC #3 : Filtrage OU ===

    def test_vendeur_voit_commandes_ou_a_seulement(self):
        """Le vendeur de l'OU A ne voit pas les commandes de l'OU B."""
        commandes_visibles = self.env['sale.order'].with_user(self.user_vendeur).search([
            ('id', 'in', [self.so_ou_a.id, self.so_ou_b.id]),
        ])
        self.assertIn(self.so_ou_a, commandes_visibles)
        self.assertNotIn(self.so_ou_b, commandes_visibles)

    # === AC #4 : Directeur voit tout ===

    def test_directeur_voit_toutes_les_commandes(self):
        """Le directeur (access_all) voit les commandes de toutes les OU."""
        commandes_visibles = self.env['sale.order'].with_user(self.user_directeur).search([
            ('id', 'in', [self.so_ou_a.id, self.so_ou_b.id]),
        ])
        self.assertIn(self.so_ou_a, commandes_visibles)
        self.assertIn(self.so_ou_b, commandes_visibles)

    def test_directeur_peut_filtrer_par_ou(self):
        """Le directeur peut filtrer les commandes par OU spécifique."""
        commandes_filtrees = self.env['sale.order'].with_user(self.user_directeur).search([
            ('id', 'in', [self.so_ou_a.id, self.so_ou_b.id]),
            ('operating_unit_id', '=', self.ou_a.id),
        ])
        self.assertIn(self.so_ou_a, commandes_filtrees)
        self.assertNotIn(self.so_ou_b, commandes_filtrees)

    def test_directeur_a_groupe_access_all(self):
        """Le directeur a le groupe operating_unit_access_all."""
        self.assertTrue(
            self.user_directeur.has_group(
                'operating_unit_access_all.group_all_operating_unit'
            ),
        )

    def test_vendeur_na_pas_access_all(self):
        """Le vendeur n'a PAS le groupe operating_unit_access_all."""
        self.assertFalse(
            self.user_vendeur.has_group(
                'operating_unit_access_all.group_all_operating_unit'
            ),
        )

    # === Propagation OU : PEC et factures (S12.2 AC#5, review M3) ===

    def _setup_pec_data(self):
        """Helper: crée les données assurance pour tester PEC et facturation."""
        self.insurer = self.env['res.partner'].create({
            'name': 'IPM Test OU',
            'is_insurer': True,
        })
        self.plan_ou = self.env['optical.insurer.plan'].create({
            'name': 'Plan OU Test',
            'insurer_id': self.insurer.id,
            'default_coverage_rate': 80.0,
            'billing_mode': 'third_party',
        })
        self.policy_ou = self.env['optical.policy'].create({
            'patient_id': self.partner.id,
            'insurer_id': self.insurer.id,
            'plan_id': self.plan_ou.id,
            'coverage_rate': 80.0,
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',
        })
        # Assign policy to SO OU A
        self.so_ou_a.policy_id = self.policy_ou.id

    def test_propagation_ou_pec(self):
        """La création d'une PEC propage l'OU du SO."""
        self._setup_pec_data()
        self.so_ou_a.action_create_pec()
        self.so_ou_a.action_confirm()
        pec = self.so_ou_a.pec_id
        self.assertTrue(pec)
        self.assertEqual(pec.operating_unit_id, self.ou_a)

    def test_propagation_ou_factures_split(self):
        """La facturation split propage l'OU du SO sur les factures."""
        self._setup_pec_data()
        self.so_ou_a.action_create_pec()
        self.so_ou_a.action_confirm()
        pec = self.so_ou_a.pec_id
        pec.action_submit()
        self.assertEqual(pec.state, 'submitted')
        pec.with_user(self.user_directeur).action_approve()
        self.assertEqual(pec.state, 'approved')
        pec.write({'amount_insurance_approved': self.so_ou_a.amount_insurance or self.so_ou_a.amount_total})
        pec.with_user(self.user_directeur).action_create_invoices()
        self.assertEqual(pec.state, 'invoiced')
        # Facture assurance
        self.assertTrue(pec.invoice_insurance_id)
        self.assertEqual(
            pec.invoice_insurance_id.operating_unit_id, self.ou_a,
        )
        # Facture TM (80% couverture → TM existe)
        self.assertTrue(pec.invoice_tm_id)
        self.assertEqual(
            pec.invoice_tm_id.operating_unit_id, self.ou_a,
        )

    def test_prescription_default_ou(self):
        """Une prescription créée avec le bridge a l'OU par défaut de l'utilisateur."""
        prescriber = self.env['res.partner'].create({
            'name': 'Dr Test OU',
            'is_prescriber': True,
            'prescriber_registration': 'OU-001',
            'prescriber_specialty': 'ophthalmologist',
        })
        prescription = self.env['optical.prescription'].with_user(
            self.user_vendeur,
        ).create({
            'patient_id': self.partner.id,
            'prescriber_id': prescriber.id,
            'od_sphere': 1.00,
            'og_sphere': 1.50,
        })
        self.assertEqual(prescription.operating_unit_id, self.ou_a)

    def test_insurer_plan_default_ou(self):
        """Un insurer plan créé avec le bridge a l'OU par défaut de l'utilisateur."""
        insurer = self.env['res.partner'].create({
            'name': 'IPM Default OU Test',
            'is_insurer': True,
        })
        plan = self.env['optical.insurer.plan'].with_user(
            self.user_directeur,
        ).create({
            'name': 'Plan Default OU',
            'insurer_id': insurer.id,
            'default_coverage_rate': 70.0,
            'billing_mode': 'third_party',
        })
        self.assertEqual(plan.operating_unit_id, self.ou_a)

    # === Propagation OU B (review H2) ===

    def test_propagation_ou_pec_ou_b(self):
        """La création d'une PEC propage l'OU B du SO (pas l'OU par défaut)."""
        insurer = self.env['res.partner'].create({
            'name': 'IPM Test OU B',
            'is_insurer': True,
        })
        plan = self.env['optical.insurer.plan'].create({
            'name': 'Plan OU B Test',
            'insurer_id': insurer.id,
            'default_coverage_rate': 80.0,
            'billing_mode': 'third_party',
        })
        policy = self.env['optical.policy'].create({
            'patient_id': self.partner.id,
            'insurer_id': insurer.id,
            'plan_id': plan.id,
            'coverage_rate': 80.0,
            'date_start': '2026-01-01',
            'date_end': '2026-12-31',
        })
        self.so_ou_b.policy_id = policy.id
        self.so_ou_b.action_create_pec()
        self.so_ou_b.action_confirm()
        pec = self.so_ou_b.pec_id
        self.assertTrue(pec)
        self.assertEqual(pec.operating_unit_id, self.ou_b)

    # === Access all : directeur voit OU non-assignée (review H3) ===

    def test_directeur_access_all_voit_ou_non_assignee(self):
        """Le directeur (access_all) voit les prescriptions d'une OU non explicitement assignée."""
        ou_c = self.env['operating.unit'].create({
            'name': 'Boutique Test C',
            'code': 'BTC',
            'partner_id': self.env.company.partner_id.id,
            'company_id': self.env.company.id,
        })
        prescriber = self.env['res.partner'].create({
            'name': 'Dr Test Access All',
            'is_prescriber': True,
            'prescriber_registration': 'AA-001',
            'prescriber_specialty': 'ophthalmologist',
        })
        rx_ou_c = self.env['optical.prescription'].create({
            'patient_id': self.partner.id,
            'prescriber_id': prescriber.id,
            'operating_unit_id': ou_c.id,
            'od_sphere': 2.00,
            'og_sphere': 2.50,
        })
        # OCA access_all ajoute automatiquement toutes les OUs
        # aux operating_unit_ids du directeur — validons ce mécanisme
        self.assertIn(ou_c, self.user_directeur.operating_unit_ids)
        # Le directeur voit la prescription de l'OU C
        visible = self.env['optical.prescription'].with_user(
            self.user_directeur,
        ).search([('id', '=', rx_ou_c.id)])
        self.assertIn(rx_ou_c, visible)
        # Le vendeur (sans access_all) ne la voit PAS
        invisible = self.env['optical.prescription'].with_user(
            self.user_vendeur,
        ).search([('id', '=', rx_ou_c.id)])
        self.assertNotIn(rx_ou_c, invisible)

    # === Record rules modeles optiques (review M2) ===

    def test_vendeur_voit_prescriptions_ou_a_seulement(self):
        """Le vendeur OU A ne voit pas les prescriptions de l'OU B."""
        prescriber = self.env['res.partner'].create({
            'name': 'Dr Test Record Rule',
            'is_prescriber': True,
            'prescriber_registration': 'RR-001',
            'prescriber_specialty': 'ophthalmologist',
        })
        rx_a = self.env['optical.prescription'].create({
            'patient_id': self.partner.id,
            'prescriber_id': prescriber.id,
            'operating_unit_id': self.ou_a.id,
            'od_sphere': 1.00,
            'og_sphere': 1.00,
        })
        rx_b = self.env['optical.prescription'].create({
            'patient_id': self.partner.id,
            'prescriber_id': prescriber.id,
            'operating_unit_id': self.ou_b.id,
            'od_sphere': 1.50,
            'og_sphere': 1.50,
        })
        visible = self.env['optical.prescription'].with_user(
            self.user_vendeur,
        ).search([('id', 'in', [rx_a.id, rx_b.id])])
        self.assertIn(rx_a, visible)
        self.assertNotIn(rx_b, visible)
