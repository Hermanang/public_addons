# -*- coding: utf-8 -*-

from odoo.tests import tagged, TransactionCase
from odoo.exceptions import AccessError


@tagged('post_install', '-at_install', 'gocardless', 'security')
class TestGoCardlessSecurity(TransactionCase):
    """Test multi-company security rules for GoCardless module"""

    def setUp(self):
        super(TestGoCardlessSecurity, self).setUp()
        
        # Create test companies
        self.company_a = self.env['res.company'].create({
            'name': 'Company A'
        })
        self.company_b = self.env['res.company'].create({
            'name': 'Company B'
        })
        
        # Create test users for each company
        self.user_a = self.env['res.users'].create({
            'name': 'User Company A',
            'login': 'user_a@test.com',
            'company_id': self.company_a.id,
            'company_ids': [(6, 0, [self.company_a.id])],
        })
        
        self.user_b = self.env['res.users'].create({
            'name': 'User Company B',
            'login': 'user_b@test.com',
            'company_id': self.company_b.id,
            'company_ids': [(6, 0, [self.company_b.id])],
        })
        
        # Create GoCardless configurations for each company
        self.config_a = self.env['gocardless.config'].create({
            'name': 'Config Company A',
            'company_id': self.company_a.id,
            'gc_client_id': 'test_client_a',
            'gc_client_secret': 'test_secret_a',
            'gc_environment': 'sandbox',
        })
        
        self.config_b = self.env['gocardless.config'].create({
            'name': 'Config Company B',
            'company_id': self.company_b.id,
            'gc_client_id': 'test_client_b',
            'gc_client_secret': 'test_secret_b',
            'gc_environment': 'sandbox',
        })

    def test_multi_company_config_access(self):
        """Test that users can only access configurations from their company"""
        
        # User A should only see config from company A
        configs_a = self.env['gocardless.config'].with_user(self.user_a).search([])
        self.assertEqual(len(configs_a), 1)
        self.assertEqual(configs_a.company_id, self.company_a)
        
        # User B should only see config from company B
        configs_b = self.env['gocardless.config'].with_user(self.user_b).search([])
        self.assertEqual(len(configs_b), 1)
        self.assertEqual(configs_b.company_id, self.company_b)

    def test_cross_company_config_access_denied(self):
        """Test that users cannot access configurations from other companies"""
        
        # User A should not be able to access config from company B
        with self.assertRaises(AccessError):
            self.config_b.with_user(self.user_a).read(['name'])
            
        # User B should not be able to access config from company A
        with self.assertRaises(AccessError):
            self.config_a.with_user(self.user_b).read(['name'])

    def test_multi_company_mandate_access(self):
        """Test that mandates are properly isolated by company"""
        
        # Create test mandates for each company
        mandate_a = self.env['gocardless.mandate'].create({
            'gc_mandate_id': 'MD0001A',
            'gc_state': 'active',
            'config_id': self.config_a.id,
        })
        
        mandate_b = self.env['gocardless.mandate'].create({
            'gc_mandate_id': 'MD0001B',
            'gc_state': 'active',
            'config_id': self.config_b.id,
        })
        
        # User A should only see mandates from company A
        mandates_a = self.env['gocardless.mandate'].with_user(self.user_a).search([])
        self.assertEqual(len(mandates_a), 1)
        self.assertEqual(mandates_a.config_id.company_id, self.company_a)
        
        # User B should only see mandates from company B
        mandates_b = self.env['gocardless.mandate'].with_user(self.user_b).search([])
        self.assertEqual(len(mandates_b), 1)
        self.assertEqual(mandates_b.config_id.company_id, self.company_b)

    def test_multi_company_payment_access(self):
        """Test that payments are properly isolated by company"""
        
        # Create test payments for each company
        payment_a = self.env['gocardless.payment'].create({
            'gc_payment_id': 'PM0001A',
            'gc_payment_state': 'pending',
            'amount': 100.0,
            'config_id': self.config_a.id,
        })
        
        payment_b = self.env['gocardless.payment'].create({
            'gc_payment_id': 'PM0001B',
            'gc_payment_state': 'pending',
            'amount': 200.0,
            'config_id': self.config_b.id,
        })
        
        # User A should only see payments from company A
        payments_a = self.env['gocardless.payment'].with_user(self.user_a).search([])
        self.assertEqual(len(payments_a), 1)
        self.assertEqual(payments_a.config_id.company_id, self.company_a)
        
        # User B should only see payments from company B
        payments_b = self.env['gocardless.payment'].with_user(self.user_b).search([])
        self.assertEqual(len(payments_b), 1)
        self.assertEqual(payments_b.config_id.company_id, self.company_b)

    def test_multi_company_event_access(self):
        """Test that events are properly isolated by company"""
        
        # Create test events for each company
        event_a = self.env['gocardless.event'].create({
            'event_id': 'EV0001A',
            'action': 'payment_created',
            'config_id': self.config_a.id,
        })
        
        event_b = self.env['gocardless.event'].create({
            'event_id': 'EV0001B',
            'action': 'payment_created',
            'config_id': self.config_b.id,
        })
        
        # User A should only see events from company A
        events_a = self.env['gocardless.event'].with_user(self.user_a).search([])
        self.assertEqual(len(events_a), 1)
        self.assertEqual(events_a.config_id.company_id, self.company_a)
        
        # User B should only see events from company B
        events_b = self.env['gocardless.event'].with_user(self.user_b).search([])
        self.assertEqual(len(events_b), 1)
        self.assertEqual(events_b.config_id.company_id, self.company_b)

    def test_company_auto_check_constraint(self):
        """Test that _check_company_auto prevents cross-company assignments"""
        
        # Create a test mandate for company A
        mandate = self.env['gocardless.mandate'].create({
            'gc_mandate_id': 'MD_TEST',
            'gc_state': 'active',
            'config_id': self.config_a.id,
        })
        
        # Try to assign a config from company B - should raise validation error
        with self.assertRaises(Exception):
            mandate.config_id = self.config_b
            
        # Verify the config is still from company A
        self.assertEqual(mandate.config_id.company_id, self.company_a)
