# -*- coding: utf-8 -*-

from odoo.tests import tagged, TransactionCase
from odoo.exceptions import ValidationError


@tagged('post_install', '-at_install', 'gocardless', 'mandate')
class TestGoCardlessMandate(TransactionCase):
    """Test GoCardless Mandate model"""

    def setUp(self):
        super(TestGoCardlessMandate, self).setUp()
        
        self.company = self.env['res.company'].create({
            'name': 'Test Company'
        })
        
        self.partner = self.env['res.partner'].create({
            'name': 'Test Partner',
            'company_id': self.company.id,
        })
        
        self.config = self.env['gocardless.config'].create({
            'name': 'Test Config',
            'company_id': self.company.id,
            'gc_client_id': 'test_client',
            'gc_client_secret': 'test_secret',
            'gc_environment': 'sandbox',
        })

    def test_mandate_creation(self):
        """Test basic mandate creation"""
        mandate = self.env['gocardless.mandate'].create({
            'gc_mandate_id': 'MD_TEST_001',
            'gc_state': 'active',
            'config_id': self.config.id,
            'partner_id': self.partner.id,
        })
        
        self.assertEqual(mandate.gc_mandate_id, 'MD_TEST_001')
        self.assertEqual(mandate.gc_state, 'active')
        self.assertEqual(mandate.config_id, self.config)
        self.assertEqual(mandate.partner_id, self.partner)
        self.assertEqual(mandate.company_id, self.company)

    def test_mandate_required_fields(self):
        """Test that required fields are enforced"""
        with self.assertRaises(ValidationError):
            # Missing gc_mandate_id
            self.env['gocardless.mandate'].create({
                'gc_state': 'active',
                'config_id': self.config.id,
            })
            
        with self.assertRaises(ValidationError):
            # Missing gc_state
            self.env['gocardless.mandate'].create({
                'gc_mandate_id': 'MD_TEST_001',
                'config_id': self.config.id,
            })
            
        with self.assertRaises(ValidationError):
            # Missing config_id
            self.env['gocardless.mandate'].create({
                'gc_mandate_id': 'MD_TEST_001',
                'gc_state': 'active',
            })

    def test_mandate_state_validation(self):
        """Test mandate state field validation"""
        valid_states = [
            'pending', 'created', 'pending_submission', 'submitted', 'active',
            'reinstated', 'cancelled', 'failed', 'consumed', 'blocked',
            'suspended_by_payer', 'expired', 'resubmission_requested', 'replaced',
            'pending_customer_approval', 'customer_approval_granted', 'customer_approval_skipped'
        ]
        
        for state in valid_states:
            mandate = self.env['gocardless.mandate'].create({
                'gc_mandate_id': f'MD_TEST_{state}',
                'gc_state': state,
                'config_id': self.config.id,
            })
            self.assertEqual(mandate.gc_state, state)
        
        with self.assertRaises(ValidationError):
            # Invalid state
            self.env['gocardless.mandate'].create({
                'gc_mandate_id': 'MD_TEST_INVALID',
                'gc_state': 'invalid_state',
                'config_id': self.config.id,
            })

    def test_mandate_partner_relation(self):
        """Test mandate-partner relationship"""
        mandate = self.env['gocardless.mandate'].create({
            'gc_mandate_id': 'MD_TEST_PARTNER',
            'gc_state': 'active',
            'config_id': self.config.id,
            'partner_id': self.partner.id,
        })
        
        # Partner should have access to mandate
        partner_mandates = self.partner.env['gocardless.mandate'].search([
            ('partner_id', '=', self.partner.id)
        ])
        self.assertIn(mandate, partner_mandates)

    def test_mandate_config_relation(self):
        """Test mandate-config relationship"""
        mandate = self.env['gocardless.mandate'].create({
            'gc_mandate_id': 'MD_TEST_CONFIG',
            'gc_state': 'active',
            'config_id': self.config.id,
        })
        
        # Config should have access to mandate
        config_mandates = self.config.env['gocardless.mandate'].search([
            ('config_id', '=', self.config.id)
        ])
        self.assertIn(mandate, config_mandates)

    def test_mandate_company_inheritance(self):
        """Test that mandate inherits company from config"""
        mandate = self.env['gocardless.mandate'].create({
            'gc_mandate_id': 'MD_TEST_COMPANY',
            'gc_state': 'active',
            'config_id': self.config.id,
        })
        
        self.assertEqual(mandate.company_id, self.config.company_id)
        self.assertEqual(mandate.company_id, self.company)

    def test_mandate_state_change_tracking(self):
        """Test mandate state change tracking"""
        mandate = self.env['gocardless.mandate'].create({
            'gc_mandate_id': 'MD_TEST_STATE',
            'gc_state': 'pending',
            'config_id': self.config.id,
        })
        
        initial_date = mandate.gc_last_state_change
        
        # Change state
        mandate.write({'gc_state': 'active'})
        
        # State change date should be updated
        self.assertNotEqual(mandate.gc_last_state_change, initial_date)

    def test_mandate_unique_constraint(self):
        """Test that gc_mandate_id should be unique"""
        self.env['gocardless.mandate'].create({
            'gc_mandate_id': 'MD_UNIQUE_001',
            'gc_state': 'active',
            'config_id': self.config.id,
        })
        
        with self.assertRaises(ValidationError):
            # Duplicate mandate ID
            self.env['gocardless.mandate'].create({
                'gc_mandate_id': 'MD_UNIQUE_001',
                'gc_state': 'pending',
                'config_id': self.config.id,
            })

    def test_mandate_display_name(self):
        """Test mandate display name"""
        mandate = self.env['gocardless.mandate'].create({
            'gc_mandate_id': 'MD_DISPLAY_001',
            'gc_state': 'active',
            'config_id': self.config.id,
            'partner_id': self.partner.id,
        })
        
        display_name = mandate.display_name
        self.assertIn(mandate.gc_mandate_id, display_name)
        self.assertIn(self.partner.name, display_name)

    def test_mandate_event_relation(self):
        """Test mandate-event relationship"""
        mandate = self.env['gocardless.mandate'].create({
            'gc_mandate_id': 'MD_EVENT_001',
            'gc_state': 'active',
            'config_id': self.config.id,
        })
        
        # Create test event linked to mandate
        event = self.env['gocardless.event'].create({
            'event_id': 'EV_MANDATE_001',
            'action': 'mandate_created',
            'config_id': self.config.id,
            'mandate_id': mandate.id,
            'resource_type': 'mandates',
        })
        
        # Mandate should have the event
        self.assertIn(event, mandate.event_ids)
        self.assertEqual(event.mandate_id, mandate)
