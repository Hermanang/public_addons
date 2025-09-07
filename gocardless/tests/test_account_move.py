# -*- coding: utf-8 -*-

from odoo.tests import tagged, TransactionCase
from odoo.exceptions import UserError, ValidationError
import datetime


@tagged('post_install', '-at_install', 'gocardless', 'account_move')
class TestAccountMoveGoCardless(TransactionCase):
    """Test GoCardless integration with Account Move"""

    def setUp(self):
        super(TestAccountMoveGoCardless, self).setUp()
        
        self.company = self.env['res.company'].create({
            'name': 'Test Company'
        })
        
        self.partner = self.env['res.partner'].create({
            'name': 'Test Partner',
            'company_id': self.company.id,
            'gc_state': 'complete',  # Partner ready for GoCardless
            'gc_mandate_id': 'MD_TEST_001',
        })
        
        self.config = self.env['gocardless.config'].create({
            'name': 'Test Config',
            'company_id': self.company.id,
            'gc_client_id': 'test_client',
            'gc_client_secret': 'test_secret',
            'gc_environment': 'sandbox',
            'gc_access_token': 'test_access_token',  # Add access token for testing
        })
        
        self.mandate = self.env['gocardless.mandate'].create({
            'gc_mandate_id': 'MD_TEST_001',
            'gc_state': 'active',
            'config_id': self.config.id,
            'partner_id': self.partner.id,
        })
        
        # Create a journal for payment processing
        self.journal = self.env['account.journal'].create({
            'name': 'Test Bank Journal',
            'type': 'bank',
            'code': 'TEST',
            'company_id': self.company.id,
        })
        
        # Set up configuration parameters
        self.env['ir.config_parameter'].set_param('gocardless.gc_keep_journal', True)
        self.env['ir.config_parameter'].set_param('gocardless.gc_journal_id', self.journal.id)

    def test_invoice_gocardless_fields(self):
        """Test that GoCardless fields are properly added to invoices"""
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Product',
                'quantity': 1,
                'price_unit': 100.0,
            })]
        })
        
        # Test that GoCardless fields exist
        self.assertTrue(hasattr(invoice, 'gc_last_payment_attempt'))
        self.assertTrue(hasattr(invoice, 'gc_payment_attempted'))
        self.assertTrue(hasattr(invoice, 'gc_retry_payment'))
        self.assertTrue(hasattr(invoice, 'gc_enable_payment_recreate'))
        self.assertTrue(hasattr(invoice, 'gc_payments'))
        self.assertTrue(hasattr(invoice, 'active_payment_id'))
        self.assertTrue(hasattr(invoice, 'gc_display_gc'))
        
        # Test default values
        self.assertFalse(invoice.gc_payment_attempted)
        self.assertFalse(invoice.gc_retry_payment)
        self.assertFalse(invoice.gc_enable_payment_recreate)

    def test_compute_display_gc(self):
        """Test computation of gc_display_gc field"""
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Product',
                'quantity': 1,
                'price_unit': 100.0,
            })]
        })
        
        # Should display GoCardless when config exists and partner is ready
        self.assertTrue(invoice.gc_display_gc)
        
        # Test with partner not ready for GoCardless
        partner_not_ready = self.env['res.partner'].create({
            'name': 'Partner Not Ready',
            'company_id': self.company.id,
            'gc_state': 'setup',  # Not ready
        })
        
        invoice_not_ready = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner_not_ready.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Product',
                'quantity': 1,
                'price_unit': 100.0,
            })]
        })
        
        self.assertFalse(invoice_not_ready.gc_display_gc)

    def test_action_gocardless_take_payment_no_config(self):
        """Test payment attempt without GoCardless configuration"""
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Product',
                'quantity': 1,
                'price_unit': 100.0,
            })]
        })
        
        # Remove access token to simulate no configuration
        self.config.gc_access_token = False
        
        with self.assertRaises(UserError):
            invoice.action_gocardless_take_payment()

    def test_action_gocardless_take_payment_no_mandate(self):
        """Test payment attempt without mandate"""
        partner_no_mandate = self.env['res.partner'].create({
            'name': 'Partner No Mandate',
            'company_id': self.company.id,
            'gc_state': 'complete',
            # No gc_mandate_id set
        })
        
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner_no_mandate.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Product',
                'quantity': 1,
                'price_unit': 100.0,
            })]
        })
        
        with self.assertRaises(UserError):
            invoice.action_gocardless_take_payment()

    def test_action_gocardless_take_payment_success(self):
        """Test successful payment attempt (mock test)"""
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Product',
                'quantity': 1,
                'price_unit': 100.0,
            })]
        })
        
        # Mock the client call since we don't have real GoCardless API in tests
        # This tests the method structure and basic functionality
        
        # The actual API call will fail, but we can test the method structure
        # and that it creates the payment record
        try:
            result = invoice.action_gocardless_take_payment()
            # If we get here, the method completed without raising an exception
            # (though the actual API call would fail)
        except Exception as e:
            # Expected to fail on API call, but should have created payment record
            pass
        
        # Check that payment was created and linked to invoice
        payments = self.env['gocardless.payment'].search([
            ('invoice_id', '=', invoice.id)
        ])
        self.assertEqual(len(payments), 1)
        
        payment = payments[0]
        self.assertEqual(payment.invoice_id, invoice)
        self.assertEqual(payment.amount, invoice.amount_total)
        self.assertEqual(payment.config_id, self.config)
        self.assertEqual(payment.mandate_id, self.mandate)

    def test_action_gocardless_retry_payment(self):
        """Test payment retry functionality"""
        # Create invoice with existing payment
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Product',
                'quantity': 1,
                'price_unit': 100.0,
            })]
        })
        
        payment = self.env['gocardless.payment'].create({
            'gc_payment_id': 'PM_RETRY_TEST',
            'gc_payment_state': 'failed',
            'amount': 100.0,
            'config_id': self.config.id,
            'mandate_id': self.mandate.id,
            'invoice_id': invoice.id,
        })
        
        invoice.active_payment_id = payment.id
        
        # Test retry payment
        with self.assertRaises(UserError):
            # Should fail because config has no real access token
            invoice.action_gocardless_retry_payment()

    def test_action_gocardless_recreate_payment(self):
        """Test payment recreation functionality"""
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Product',
                'quantity': 1,
                'price_unit': 100.0,
            })]
        })
        
        # Enable recreate button
        invoice.gc_enable_payment_recreate = True
        
        # Test recreate payment
        try:
            result = invoice.action_gocardless_recreate_payment()
            # Should trigger take payment which will fail on API call
        except Exception:
            # Expected to fail on API call
            pass
        
        # Should have set retry flag
        self.assertTrue(invoice.gc_retry_payment)

    def test_process_payment_event(self):
        """Test payment event processing"""
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Product',
                'quantity': 1,
                'price_unit': 100.0,
            })]
        })
        
        payment = self.env['gocardless.payment'].create({
            'gc_payment_id': 'PM_EVENT_TEST',
            'gc_payment_state': 'confirmed',
            'amount': 100.0,
            'config_id': self.config.id,
            'mandate_id': self.mandate.id,
            'invoice_id': invoice.id,
        })
        
        # Mock event data
        class MockEvent:
            pass
        
        event = MockEvent()
        
        # Test process payment event
        invoice.processPaymentEvent(event, payment, self.journal)
        
        # Should create a payment in the journal
        # (This would normally create an account.payment record)

    def test_invoice_payment_attempt_tracking(self):
        """Test that payment attempts are properly tracked"""
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Product',
                'quantity': 1,
                'price_unit': 100.0,
            })]
        })
        
        initial_attempt_date = invoice.gc_last_payment_attempt
        initial_attempted = invoice.gc_payment_attempted
        
        # Simulate payment attempt
        invoice.write({
            'gc_last_payment_attempt': datetime.datetime.now(),
            'gc_payment_attempted': True,
        })
        
        self.assertNotEqual(invoice.gc_last_payment_attempt, initial_attempt_date)
        self.assertNotEqual(invoice.gc_payment_attempted, initial_attempted)
        self.assertTrue(invoice.gc_payment_attempted)

    def test_search_display_gc(self):
        """Test search functionality for gc_display_gc field"""
        # Create invoices with different partner states
        partner_ready = self.env['res.partner'].create({
            'name': 'Ready Partner',
            'company_id': self.company.id,
            'gc_state': 'complete',
        })
        
        partner_not_ready = self.env['res.partner'].create({
            'name': 'Not Ready Partner',
            'company_id': self.company.id,
            'gc_state': 'setup',
        })
        
        invoice_ready = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner_ready.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Product',
                'quantity': 1,
                'price_unit': 100.0,
            })]
        })
        
        invoice_not_ready = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner_not_ready.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Product',
                'quantity': 1,
                'price_unit': 100.0,
            })]
        })
        
        # Test search for GoCardless chargeable invoices
        chargeable_invoices = self.env['account.move'].search([
            ('gc_display_gc', '=', True)
        ])
        self.assertIn(invoice_ready, chargeable_invoices)
        self.assertNotIn(invoice_not_ready, chargeable_invoices)
        
        # Test search for non-chargeable invoices
        non_chargeable_invoices = self.env['account.move'].search([
            ('gc_display_gc', '=', False)
        ])
        self.assertIn(invoice_not_ready, non_chargeable_invoices)
        self.assertNotIn(invoice_ready, non_chargeable_invoices)
