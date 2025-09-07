# -*- coding: utf-8 -*-

from odoo.tests import tagged, TransactionCase
from odoo.exceptions import ValidationError


@tagged('post_install', '-at_install', 'gocardless', 'config')
class TestGoCardlessConfig(TransactionCase):
    """Test GoCardless Configuration model"""

    def setUp(self):
        super(TestGoCardlessConfig, self).setUp()
        
        self.company = self.env['res.company'].create({
            'name': 'Test Company'
        })

    def test_config_creation_with_default_name(self):
        """Test configuration creation with default name generation"""
        config = self.env['gocardless.config'].create({
            'company_id': self.company.id,
            'gc_client_id': 'test_client',
            'gc_client_secret': 'test_secret',
            'gc_environment': 'sandbox',
        })
        
        # Should have auto-generated name with company name
        expected_name = f"GoCardless - {self.company.name}"
        self.assertEqual(config.name, expected_name)

    def test_config_creation_with_custom_name(self):
        """Test configuration creation with custom name"""
        custom_name = "Custom Configuration Name"
        config = self.env['gocardless.config'].create({
            'name': custom_name,
            'company_id': self.company.id,
            'gc_client_id': 'test_client',
            'gc_client_secret': 'test_secret',
            'gc_environment': 'sandbox',
        })
        
        self.assertEqual(config.name, custom_name)

    def test_config_required_fields(self):
        """Test that required fields are enforced"""
        with self.assertRaises(ValidationError):
            # Missing company_id
            self.env['gocardless.config'].create({
                'name': 'Test Config',
                'gc_client_id': 'test_client',
                'gc_client_secret': 'test_secret',
                'gc_environment': 'sandbox',
            })

    def test_config_active_field(self):
        """Test the active field behavior"""
        config = self.env['gocardless.config'].create({
            'name': 'Test Config',
            'company_id': self.company.id,
            'gc_client_id': 'test_client',
            'gc_client_secret': 'test_secret',
            'gc_environment': 'sandbox',
        })
        
        # Should be active by default
        self.assertTrue(config.active)
        
        # Test archiving
        config.active = False
        self.assertFalse(config.active)
        
        # Test reactivating
        config.active = True
        self.assertTrue(config.active)

    def test_get_active_config_method(self):
        """Test the get_active_config method"""
        # Create active config
        active_config = self.env['gocardless.config'].create({
            'name': 'Active Config',
            'company_id': self.company.id,
            'gc_client_id': 'test_client',
            'gc_client_secret': 'test_secret',
            'gc_environment': 'sandbox',
            'active': True,
        })
        
        # Create inactive config
        inactive_config = self.env['gocardless.config'].create({
            'name': 'Inactive Config',
            'company_id': self.company.id,
            'gc_client_id': 'test_client2',
            'gc_client_secret': 'test_secret2',
            'gc_environment': 'sandbox',
            'active': False,
        })
        
        # Should return active config
        result = self.env['gocardless.config'].get_active_config(self.company.id)
        self.assertEqual(result, active_config)
        
        # Archive active config and test no active config found
        active_config.active = False
        result = self.env['gocardless.config'].get_active_config(self.company.id)
        self.assertFalse(result)

    def test_config_environment_validation(self):
        """Test environment field validation"""
        with self.assertRaises(ValidationError):
            self.env['gocardless.config'].create({
                'name': 'Test Config',
                'company_id': self.company.id,
                'gc_client_id': 'test_client',
                'gc_client_secret': 'test_secret',
                'gc_environment': 'invalid_environment',  # Invalid value
            })

    def test_config_display_name(self):
        """Test display name computation"""
        config = self.env['gocardless.config'].create({
            'name': 'Test Config',
            'company_id': self.company.id,
            'gc_client_id': 'test_client',
            'gc_client_secret': 'test_secret',
            'gc_environment': 'sandbox',
        })
        
        # Display name should include company name for clarity
        display_name = config.display_name
        self.assertIn(config.name, display_name)
        self.assertIn(self.company.name, display_name)

    def test_config_unique_per_company(self):
        """Test that only one active config per company is recommended"""
        # Create first active config
        config1 = self.env['gocardless.config'].create({
            'name': 'Config 1',
            'company_id': self.company.id,
            'gc_client_id': 'test_client1',
            'gc_client_secret': 'test_secret1',
            'gc_environment': 'sandbox',
            'active': True,
        })
        
        # Create second active config - should be allowed but not recommended
        config2 = self.env['gocardless.config'].create({
            'name': 'Config 2',
            'company_id': self.company.id,
            'gc_client_id': 'test_client2',
            'gc_client_secret': 'test_secret2',
            'gc_environment': 'sandbox',
            'active': True,
        })
        
        # Both should exist
        self.assertEqual(len(self.env['gocardless.config'].search([
            ('company_id', '=', self.company.id),
            ('active', '=', True)
        ])), 2)
        
        # But get_active_config should return the first one found
        result = self.env['gocardless.config'].get_active_config(self.company.id)
        self.assertIn(result, [config1, config2])
