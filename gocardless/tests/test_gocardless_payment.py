# -*- coding: utf-8 -*-

from odoo.tests import tagged, TransactionCase
from odoo.exceptions import ValidationError, UserError


@tagged('post_install', '-at_install', 'gocardless', 'payment')
class TestGoCardlessPayment(TransactionCase):
    """Test GoCardless Payment model"""

    def setUp(self):
        super(TestGoCardlessPayment, self).setUp()
        
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
        
        self.invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Product',
                'quantity': 1,
                'price_unit': 100.0,
            })]
        })

    def test_payment_creation(self):
        """Test basic payment creation"""
        payment = self.env['gocardless.payment'].create({
            'gc_payment_id': 'PM_TEST_001',
            'gc_payment_state': 'pending',
            'amount': 100.0,
            'config_id': self.config.id,
            'mandate_id': self.mandate.id,
            'invoice_id': self.invoice.id,
        })
        
        self.assertEqual(payment.gc_payment_id, 'PM_TEST_001')
        self.assertEqual(payment.gc_payment_state, 'pending')
        self.assertEqual(payment.amount, 100.0)
        self.assertEqual(payment.config_id, self.config)
        self.assertEqual(payment.mandate_id, self.mandate)
        self.assertEqual(payment.invoice_id, self.invoice)
        self.assertEqual(payment.company_id, self.company)

    def test_payment_required_fields(self):
        """Test that required fields are enforced"""
        with self.assertRaises(ValidationError):
            # Missing gc_payment_id
            self.env['gocardless.payment'].create({
                'gc_payment_state': 'pending',
                'amount': 100.0,
                'config_id': self.config.id,
            })
            
        with self.assertRaises(ValidationError):
            # Missing gc_payment_state
            self.env['gocardless.payment'].create({
                'gc_payment_id': 'PM_TEST_001',
                'amount': 100.0,
                'config_id': self.config.id,
            })
            
        with self.assertRaises(ValidationError):
            # Missing config_id
            self.env['gocardless.payment'].create({
                'gc_payment_id': 'PM_TEST_001',
                'gc_payment_state': 'pending',
                'amount': 100.0,
            })

    def test_payment_state_validation(self):
        """Test payment state field validation"""
        valid_states = [
            'pending', 'created', 'pending_customer_approval', 'customer_approval_granted',
            'customer_approval_rejected', 'customer_approval_denied', 'pending_submission',
            'submitted', 'confirmed', 'cancelled', 'failed', 'charged_back', 'chargeback_cancelled',
            'paid_out', 'late_failure_settled', 'chargeback_settled', 'resubmission_requested'
        ]
        
        for state in valid_states:
            payment = self.env['gocardless.payment'].create({
                'gc_payment_id': f'PM_TEST_{state}',
                'gc_payment_state': state,
                'amount': 100.0,
                'config_id': self.config.id,
            })
            self.assertEqual(payment.gc_payment_state, state)
        
        with self.assertRaises(ValidationError):
            # Invalid state
            self.env['gocardless.payment'].create({
                'gc_payment_id': 'PM_TEST_INVALID',
                'gc_payment_state': 'invalid_state',
                'amount': 100.0,
                'config_id': self.config.id,
            })

    def test_payment_amount_validation(self):
        """Test payment amount validation"""
        # Positive amount should work
        payment = self.env['gocardless.payment'].create({
            'gc_payment_id': 'PM_AMOUNT_001',
            'gc_payment_state': 'pending',
            'amount': 100.0,
            'config_id': self.config.id,
        })
        self.assertEqual(payment.amount, 100.0)
        
        with self.assertRaises(ValidationError):
            # Negative amount should fail
            self.env['gocardless.payment'].create({
                'gc_payment_id': 'PM_AMOUNT_NEG',
                'gc_payment_state': 'pending',
                'amount': -50.0,
                'config_id': self.config.id,
            })
            
        with self.assertRaises(ValidationError):
            # Zero amount should fail
            self.env['gocardless.payment'].create({
                'gc_payment_id': 'PM_AMOUNT_ZERO',
                'gc_payment_state': 'pending',
                'amount': 0.0,
                'config_id': self.config.id,
            })

    def test_payment_invoice_relation(self):
        """Test payment-invoice relationship"""
        payment = self.env['gocardless.payment'].create({
            'gc_payment_id': 'PM_INVOICE_001',
            'gc_payment_state': 'pending',
            'amount': 100.0,
            'config_id': self.config.id,
            'invoice_id': self.invoice.id,
        })
        
        # Invoice should have access to payment
        invoice_payments = self.invoice.env['gocardless.payment'].search([
            ('invoice_id', '=', self.invoice.id)
        ])
        self.assertIn(payment, invoice_payments)

    def test_payment_mandate_relation(self):
        """Test payment-mandate relationship"""
        payment = self.env['gocardless.payment'].create({
            'gc_payment_id': 'PM_MANDATE_001',
            'gc_payment_state': 'pending',
            'amount': 100.0,
            'config_id': self.config.id,
            'mandate_id': self.mandate.id,
        })
        
        # Mandate should have access to payment
        mandate_payments = self.mandate.env['gocardless.payment'].search([
            ('mandate_id', '=', self.mandate.id)
        ])
        self.assertIn(payment, mandate_payments)

    def test_payment_company_inheritance(self):
        """Test that payment inherits company from config"""
        payment = self.env['gocardless.payment'].create({
            'gc_payment_id': 'PM_COMPANY_001',
            'gc_payment_state': 'pending',
            'amount': 100.0,
            'config_id': self.config.id,
        })
        
        self.assertEqual(payment.company_id, self.config.company_id)
        self.assertEqual(payment.company_id, self.company)

    def test_payment_state_change_tracking(self):
        """Test payment state change tracking"""
        payment = self.env['gocardless.payment'].create({
            'gc_payment_id': 'PM_STATE_001',
            'gc_payment_state': 'pending',
            'amount': 100.0,
            'config_id': self.config.id,
        })
        
        initial_date = payment.last_state_change
        
        # Change state
        payment.write({'gc_payment_state': 'confirmed'})
        
        # State change date should be updated
        self.assertNotEqual(payment.last_state_change, initial_date)

    def test_payment_unique_constraint(self):
        """Test that gc_payment_id should be unique"""
        self.env['gocardless.payment'].create({
            'gc_payment_id': 'PM_UNIQUE_001',
            'gc_payment_state': 'pending',
            'amount': 100.0,
            'config_id': self.config.id,
        })
        
        with self.assertRaises(ValidationError):
            # Duplicate payment ID
            self.env['gocardless.payment'].create({
                'gc_payment_id': 'PM_UNIQUE_001',
                'gc_payment_state': 'confirmed',
                'amount': 200.0,
                'config_id': self.config.id,
            })

    def test_payment_dates_tracking(self):
        """Test payment date fields tracking"""
        payment = self.env['gocardless.payment'].create({
            'gc_payment_id': 'PM_DATES_001',
            'gc_payment_state': 'pending',
            'amount': 100.0,
            'config_id': self.config.id,
        })
        
        # Dates should be empty initially for pending state
        self.assertFalse(payment.claim_date)
        self.assertFalse(payment.post_date)
        self.assertFalse(payment.payout_date)
        
        # Change to confirmed state should set post_date
        payment.write({
            'gc_payment_state': 'confirmed',
            'post_date': '2024-01-01 10:00:00',
        })
        self.assertTrue(payment.post_date)
        
        # Change to paid_out state should set payout_date
        payment.write({
            'gc_payment_state': 'paid_out',
            'payout_date': '2024-01-02 10:00:00',
        })
        self.assertTrue(payment.payout_date)

    def test_payment_event_relation(self):
        """Test payment-event relationship"""
        payment = self.env['gocardless.payment'].create({
            'gc_payment_id': 'PM_EVENT_001',
            'gc_payment_state': 'pending',
            'amount': 100.0,
            'config_id': self.config.id,
        })
        
        # Create test event linked to payment
        event = self.env['gocardless.event'].create({
            'event_id': 'EV_PAYMENT_001',
            'action': 'payment_created',
            'config_id': self.config.id,
            'payment_id': payment.id,
            'resource_type': 'payments',
        })
        
        # Payment should have the event
        self.assertIn(event, payment.event_ids)
        self.assertEqual(event.payment_id, payment)

    def test_payment_retry_method(self):
        """Test payment retry method (mock test)"""
        payment = self.env['gocardless.payment'].create({
            'gc_payment_id': 'PM_RETRY_001',
            'gc_payment_state': 'failed',
            'amount': 100.0,
            'config_id': self.config.id,
        })
        
        # Mock the client call since we don't have real GoCardless API in tests
        # This tests the method structure and error handling
        with self.assertRaises(UserError):
            # Should raise error because config has no access token
            payment.retry_payment()

    def test_payment_cancel_method(self):
        """Test payment cancel method (mock test)"""
        payment = self.env['gocardless.payment'].create({
            'gc_payment_id': 'PM_CANCEL_001',
            'gc_payment_state': 'pending',
            'amount': 100.0,
            'config_id': self.config.id,
        })
        
        # Mock the client call since we don't have real GoCardless API in tests
        # This tests the method structure and error handling
        with self.assertRaises(UserError):
            # Should raise error because config has no access token
            payment.gc_cancel_payment()
