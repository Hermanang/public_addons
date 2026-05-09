# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestHelpdeskTypeStageValidation(TransactionCase):
    """Tests du module bridge : la validation des champs par stage est filtrable
    par type via validate_type_ids."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Client Test Type Stage Validation',
            'customer_rank': 1,
        })
        cls.team = cls.env['helpdesk.ticket.team'].create({
            'name': 'Equipe Test Type Stage Validation',
        })
        cls.type_a = cls.env['helpdesk.ticket.type'].create({
            'name': 'Type A',
        })
        cls.type_b = cls.env['helpdesk.ticket.type'].create({
            'name': 'Type B',
        })
        cls.stage = cls.env['helpdesk.ticket.stage'].create({
            'name': 'Stage Test Validation',
            'sequence': 1,
            'closed': False,
        })
        # Champ partner_email : Char qui peut etre False (au contraire de priority='0' qui est truthy)
        cls.field_partner_email = cls.env['ir.model.fields'].search([
            ('model', '=', 'helpdesk.ticket'),
            ('name', '=', 'partner_email'),
        ], limit=1)

    def _create_ticket(self, type_id=False, partner_email=False):
        return self.env['helpdesk.ticket'].create({
            'name': 'Test ticket',
            'partner_id': self.partner.id,
            'team_id': self.team.id,
            'type_id': type_id,
            'partner_email': partner_email,
            'description': '<p>x</p>',
        })

    def test_no_type_filter_validates_all_types(self):
        """validate_type_ids vide : la validation s'applique a tous les tickets."""
        self.stage.write({
            'validate_field_ids': [(6, 0, [self.field_partner_email.id])],
            'validate_type_ids': [(6, 0, [])],
        })
        ticket = self._create_ticket(type_id=self.type_a.id, partner_email=False)
        with self.assertRaises(ValidationError):
            ticket.stage_id = self.stage

    def test_type_filter_skips_validation_for_other_types(self):
        """validate_type_ids = [Type A] : valide seulement Type A, ignore Type B."""
        self.stage.write({
            'validate_field_ids': [(6, 0, [self.field_partner_email.id])],
            'validate_type_ids': [(6, 0, [self.type_a.id])],
        })
        # Type A sans email -> doit echouer
        t_a = self._create_ticket(type_id=self.type_a.id, partner_email=False)
        with self.assertRaises(ValidationError):
            t_a.stage_id = self.stage

        # Type B sans email -> doit passer (skipped)
        t_b = self._create_ticket(type_id=self.type_b.id, partner_email=False)
        t_b.stage_id = self.stage
        self.assertEqual(t_b.stage_id, self.stage)

    def test_type_filter_with_matching_type_validates(self):
        """validate_type_ids = [Type A] : Type A avec champs OK passe."""
        self.stage.write({
            'validate_field_ids': [(6, 0, [self.field_partner_email.id])],
            'validate_type_ids': [(6, 0, [self.type_a.id])],
        })
        t_a = self._create_ticket(type_id=self.type_a.id, partner_email='test@example.com')
        t_a.stage_id = self.stage
        self.assertEqual(t_a.stage_id, self.stage)

    def test_ticket_without_type_skipped_when_filter_set(self):
        """validate_type_ids = [Type A] : ticket sans type est skipped."""
        self.stage.write({
            'validate_field_ids': [(6, 0, [self.field_partner_email.id])],
            'validate_type_ids': [(6, 0, [self.type_a.id])],
        })
        ticket = self._create_ticket(type_id=False, partner_email=False)
        ticket.stage_id = self.stage
        self.assertEqual(ticket.stage_id, self.stage)

    def test_stage_without_validation_passes_all(self):
        """Stage sans validate_field_ids ni validate_type_ids : aucune
        validation, tous les tickets passent (comportement par défaut
        helpdesk_mgmt préservé)."""
        # Stage sans aucune config de validation
        self.stage.write({
            'validate_field_ids': [(6, 0, [])],
            'validate_type_ids': [(6, 0, [])],
        })
        # Ticket sans email ni type → doit passer (rien à valider)
        ticket = self._create_ticket(type_id=False, partner_email=False)
        ticket.stage_id = self.stage
        self.assertEqual(ticket.stage_id, self.stage)
        # Ticket avec type → doit passer aussi
        ticket2 = self._create_ticket(type_id=self.type_a.id, partner_email=False)
        ticket2.stage_id = self.stage
        self.assertEqual(ticket2.stage_id, self.stage)
