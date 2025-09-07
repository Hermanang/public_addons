# -*- coding: utf-8 -*-

from odoo.tests import tagged, TransactionCase
from odoo.exceptions import ValidationError
import datetime


@tagged('post_install', '-at_install', 'gocardless', 'event')
class TestGoCardlessEvent(TransactionCase):
    """Test GoCardless Event model"""

    def setUp(self):
        super(TestGoCardlessEvent, self).setUp()
        
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
        
        self.mandate = self.env['gocardless.mandate'].create({
            'gc_mandate_id': 'MD_TEST_001',
            'gc_state': 'active',
            'config_id': self.config.id,
            'partner_id': self.partner.id,
        })
        
        self.payment = self.env['gocardless.payment'].create({
            'gc_payment_id': 'PM_TEST_001',
            'gc_payment_state': 'pending',
            'amount': 100.0,
            'config_id': self.config.id,
            'mandate_id': self.mandate.id,
        })

    def test_event_creation(self):
        """Test basic event creation"""
        event = self.env['gocardless.event'].create({
            'event_id': 'EV_TEST_001',
            'action': 'payment_created',
            'created_at': datetime.datetime.now(),
            'config_id': self.config.id,
            'resource_type': 'payments',
            'payment_id': self.payment.id,
        })
        
        self.assertEqual(event.event_id, 'EV_TEST_001')
        self.assertEqual(event.action, 'payment_created')
        self.assertEqual(event.config_id, self.config)
        self.assertEqual(event.resource_type, 'payments')
        self.assertEqual(event.payment_id, self.payment)
        self.assertEqual(event.company_id, self.company)

    def test_event_required_fields(self):
        """Test that required fields are enforced"""
        with self.assertRaises(ValidationError):
            # Missing event_id
            self.env['gocardless.event'].create({
                'action': 'payment_created',
                'config_id': self.config.id,
                'resource_type': 'payments',
            })
            
        with self.assertRaises(ValidationError):
            # Missing action
            self.env['gocardless.event'].create({
                'event_id': 'EV_TEST_001',
                'config_id': self.config.id,
                'resource_type': 'payments',
            })
            
        with self.assertRaises(ValidationError):
            # Missing config_id
            self.env['gocardless.event'].create({
                'event_id': 'EV_TEST_001',
                'action': 'payment_created',
                'resource_type': 'payments',
            })
            
        with self.assertRaises(ValidationError):
            # Missing resource_type
            self.env['gocardless.event'].create({
                'event_id': 'EV_TEST_001',
                'action': 'payment_created',
                'config_id': self.config.id,
            })

    def test_event_resource_type_validation(self):
        """Test event resource type field validation"""
        valid_resource_types = [
            'payments', 'mandates', 'payouts', 'refunds', 'subscriptions',
            'creditors', 'billing_requests', 'instalment_schedules', 'payer_authorisations'
        ]
        
        for resource_type in valid_resource_types:
            event = self.env['gocardless.event'].create({
                'event_id': f'EV_TEST_{resource_type}',
                'action': 'created',
                'config_id': self.config.id,
                'resource_type': resource_type,
            })
            self.assertEqual(event.resource_type, resource_type)
        
        with self.assertRaises(ValidationError):
            # Invalid resource type
            self.env['gocardless.event'].create({
                'event_id': 'EV_TEST_INVALID',
                'action': 'created',
                'config_id': self.config.id,
                'resource_type': 'invalid_resource',
            })

    def test_event_origin_validation(self):
        """Test event origin field validation"""
        valid_origins = ['bank', 'gocardless', 'api', 'customer', 'payer']
        
        for origin in valid_origins:
            event = self.env['gocardless.event'].create({
                'event_id': f'EV_ORIGIN_{origin}',
                'action': 'created',
                'config_id': self.config.id,
                'resource_type': 'payments',
                'ev_origin': origin,
            })
            self.assertEqual(event.ev_origin, origin)
        
        with self.assertRaises(ValidationError):
            # Invalid origin
            self.env['gocardless.event'].create({
                'event_id': 'EV_ORIGIN_INVALID',
                'action': 'created',
                'config_id': self.config.id,
                'resource_type': 'payments',
                'ev_origin': 'invalid_origin',
            })

    def test_event_payment_relation(self):
        """Test event-payment relationship"""
        event = self.env['gocardless.event'].create({
            'event_id': 'EV_PAYMENT_001',
            'action': 'payment_created',
            'config_id': self.config.id,
            'resource_type': 'payments',
            'payment_id': self.payment.id,
        })
        
        # Payment should have access to event
        payment_events = self.payment.env['gocardless.event'].search([
            ('payment_id', '=', self.payment.id)
        ])
        self.assertIn(event, payment_events)

    def test_event_mandate_relation(self):
        """Test event-mandate relationship"""
        event = self.env['gocardless.event'].create({
            'event_id': 'EV_MANDATE_001',
            'action': 'mandate_created',
            'config_id': self.config.id,
            'resource_type': 'mandates',
            'mandate_id': self.mandate.id,
        })
        
        # Mandate should have access to event
        mandate_events = self.mandate.env['gocardless.event'].search([
            ('mandate_id', '=', self.mandate.id)
        ])
        self.assertIn(event, mandate_events)

    def test_event_company_inheritance(self):
        """Test that event inherits company from config"""
        event = self.env['gocardless.event'].create({
            'event_id': 'EV_COMPANY_001',
            'action': 'payment_created',
            'config_id': self.config.id,
            'resource_type': 'payments',
        })
        
        self.assertEqual(event.company_id, self.config.company_id)
        self.assertEqual(event.company_id, self.company)

    def test_event_unique_constraint(self):
        """Test that event_id should be unique"""
        self.env['gocardless.event'].create({
            'event_id': 'EV_UNIQUE_001',
            'action': 'payment_created',
            'config_id': self.config.id,
            'resource_type': 'payments',
        })
        
        with self.assertRaises(ValidationError):
            # Duplicate event ID
            self.env['gocardless.event'].create({
                'event_id': 'EV_UNIQUE_001',
                'action': 'mandate_created',
                'config_id': self.config.id,
                'resource_type': 'mandates',
            })

    def test_event_display_name(self):
        """Test event display name"""
        event = self.env['gocardless.event'].create({
            'event_id': 'EV_DISPLAY_001',
            'action': 'payment_created',
            'config_id': self.config.id,
            'resource_type': 'payments',
            'payment_id': self.payment.id,
        })
        
        display_name = event.display_name
        self.assertIn(event.event_id, display_name)
        self.assertIn(event.action, display_name)

    def test_event_cause_and_description(self):
        """Test event cause and description fields"""
        event = self.env['gocardless.event'].create({
            'event_id': 'EV_CAUSE_001',
            'action': 'payment_failed',
            'config_id': self.config.id,
            'resource_type': 'payments',
            'cause': 'insufficient_funds',
            'ev_description': 'Customer account has insufficient funds',
        })
        
        self.assertEqual(event.cause, 'insufficient_funds')
        self.assertEqual(event.ev_description, 'Customer account has insufficient funds')

    def test_event_reason_code_and_scheme(self):
        """Test event reason code and scheme fields"""
        event = self.env['gocardless.event'].create({
            'event_id': 'EV_REASON_001',
            'action': 'payment_failed',
            'config_id': self.config.id,
            'resource_type': 'payments',
            'ev_reason_code': 'R1',
            'ev_scheme': 'bacs',
        })
        
        self.assertEqual(event.ev_reason_code, 'R1')
        self.assertEqual(event.ev_scheme, 'bacs')

    def test_event_process_methods(self):
        """Test event processing methods (mock tests)"""
        event = self.env['gocardless.event'].create({
            'event_id': 'EV_PROCESS_001',
            'action': 'payment_created',
            'config_id': self.config.id,
            'resource_type': 'payments',
        })
        
        # Test that methods exist and can be called
        # These are mostly integration tests that would require mocking
        event.do_full_event_refresh()
        event.doEvents()
        
        # The actual process_events method would require mocking the GoCardless client
        # This just tests that the method exists and can be called without errors
        # in a basic way (it will fail on API calls but that's expected)

    def test_event_dispatch_methods(self):
        """Test event dispatch methods"""
        event = self.env['gocardless.event'].create({
            'event_id': 'EV_DISPATCH_001',
            'action': 'payment_created',
            'config_id': self.config.id,
            'resource_type': 'payments',
        })
        
        # Test that dispatch methods exist
        # These would normally process real GoCardless events
        # For unit tests, we just verify the methods exist
        self.assertTrue(hasattr(event, 'dispatchPaymentEvents'))
        self.assertTrue(hasattr(event, 'dispatchMandateEvents'))
        
        # The actual dispatch would require proper event data structure
        # which would come from the GoCardless API
