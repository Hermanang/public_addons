# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestEmailPec(OpticalTestCommon):
    """Tests Story 6.4 : Notification email assureur depuis la PEC (FR64)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Configurer l'email sur l'assureur pour les tests
        cls.insurer.write({'email': 'ipm@test.com'})
        # Creer une PEC en etat draft pour les tests
        cls.pec = cls._create_pec()

    def test_01_send_to_insurer_opens_wizard(self):
        """AC#1 : Le bouton retourne une action window mail.compose.message avec template."""
        result = self.pec.with_user(self.user_vendeur).action_send_to_insurer()

        self.assertEqual(result['type'], 'ir.actions.act_window')
        self.assertEqual(result['res_model'], 'mail.compose.message')
        self.assertEqual(result['target'], 'new')

        ctx = result['context']
        self.assertEqual(ctx['default_model'], 'optical.pec')
        self.assertEqual(ctx['default_res_ids'], self.pec.ids)
        self.assertTrue(ctx.get('default_template_id'))
        self.assertEqual(ctx['default_composition_mode'], 'comment')

        # Verifier que le template est bien celui attendu
        template = self.env.ref('optical.email_template_pec_request')
        self.assertEqual(ctx['default_template_id'], template.id)

    def test_02_send_to_insurer_no_email_raises(self):
        """AC#4 : UserError si assureur sans email."""
        self.insurer.write({'email': False})
        with self.assertRaises(UserError):
            self.pec.with_user(self.user_vendeur).action_send_to_insurer()
        # Restaurer l'email pour les autres tests
        self.insurer.write({'email': 'ipm@test.com'})

    def test_03_send_transitions_draft_to_submitted(self):
        """AC#3 : Envoi depuis PEC draft → state passe a submitted."""
        self.assertEqual(self.pec.state, 'draft')

        # Simuler l'envoi via message_post avec le contexte mark_pec_submitted
        self.pec.with_context(mark_pec_submitted=True).message_post(
            body="Test envoi email",
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        self.assertEqual(self.pec.state, 'submitted')

    def test_04_send_from_submitted_stays_submitted(self):
        """AC#3 : Envoi depuis PEC submitted → state reste submitted."""
        self.pec.action_submit()
        self.assertEqual(self.pec.state, 'submitted')

        # Simuler un 2e envoi depuis l'etat submitted
        self.pec.with_context(mark_pec_submitted=True).message_post(
            body="Test re-envoi email",
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        self.assertEqual(self.pec.state, 'submitted')

    def test_05_submit_without_email_still_works(self):
        """AC#5 : Le bouton Soumettre fonctionne independamment."""
        # Creer une nouvelle PEC pour ce test
        order2 = self.env['sale.order'].create({
            'partner_id': self.patient.id,
            'policy_id': self.policy.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product_monture.id,
                    'product_uom_qty': 1,
                    'price_unit': 50000.0,
                }),
            ],
        })
        order2.action_create_pec()
        order2.action_confirm()
        pec2 = order2.pec_id

        self.assertEqual(pec2.state, 'draft')
        pec2.action_submit()
        self.assertEqual(pec2.state, 'submitted')

    def test_06_prescription_attachment_included(self):
        """AC#1 : Si ordonnance a une piece jointe, elle est incluse dans l'action."""
        # Lier une ordonnance a la commande (et donc a la PEC via champ related)
        self.sale_order.write({'prescription_id': self.prescription_confirmed.id})
        self.assertTrue(self.pec.prescription_id, "La PEC doit avoir une ordonnance liee")

        # Creer une piece jointe sur l'ordonnance
        attachment = self.env['ir.attachment'].create({
            'name': 'ordonnance_test.pdf',
            'type': 'binary',
            'datas': 'dGVzdA==',  # base64 de "test"
            'res_model': 'optical.prescription',
            'res_id': self.pec.prescription_id.id,
            'mimetype': 'application/pdf',
        })
        self.pec.prescription_id.write({
            'message_main_attachment_id': attachment.id,
        })

        result = self.pec.with_user(self.user_vendeur).action_send_to_insurer()
        ctx = result['context']

        # Verifier que les attachment_ids contiennent l'ordonnance
        self.assertTrue(
            ctx.get('default_attachment_ids'),
            "default_attachment_ids doit etre present quand une ordonnance a une piece jointe",
        )
        attachment_cmd = ctx['default_attachment_ids'][0]
        attachment_ids = attachment_cmd[2] if len(attachment_cmd) > 2 else []
        self.assertIn(attachment.id, attachment_ids)

    def test_07_policy_attachment_included(self):
        """CC-2026-03-10 : Si police a une piece jointe principale, elle est incluse dans l'action."""
        # Creer une piece jointe sur la police
        attachment = self.env['ir.attachment'].create({
            'name': 'carte_police_test.pdf',
            'type': 'binary',
            'datas': 'dGVzdA==',  # base64 de "test"
            'res_model': 'optical.policy',
            'res_id': self.policy.id,
            'mimetype': 'application/pdf',
        })
        self.policy.write({
            'message_main_attachment_id': attachment.id,
        })

        result = self.pec.action_send_to_insurer()
        ctx = result['context']

        self.assertTrue(
            ctx.get('default_attachment_ids'),
            "default_attachment_ids doit etre present quand la police a une piece jointe",
        )
        attachment_cmd = ctx['default_attachment_ids'][0]
        attachment_ids = attachment_cmd[2] if len(attachment_cmd) > 2 else []
        self.assertIn(attachment.id, attachment_ids)

    def test_08_policy_no_attachment_no_error(self):
        """CC-2026-03-10 : Sans piece jointe principale sur la police, pas d'erreur."""
        # S'assurer que la police n'a pas de piece jointe principale
        self.policy.write({'message_main_attachment_id': False})

        result = self.pec.action_send_to_insurer()
        # Pas d'erreur, le wizard s'ouvre normalement
        self.assertEqual(result['type'], 'ir.actions.act_window')
        self.assertEqual(result['res_model'], 'mail.compose.message')

    def test_09_prescription_and_policy_attachments_combined(self):
        """CC-2026-03-10 : Ordonnance + police PJ incluses simultanement."""
        # Lier ordonnance
        self.sale_order.write({'prescription_id': self.prescription_confirmed.id})
        presc_att = self.env['ir.attachment'].create({
            'name': 'ordonnance.pdf',
            'type': 'binary',
            'datas': 'dGVzdA==',
            'res_model': 'optical.prescription',
            'res_id': self.pec.prescription_id.id,
            'mimetype': 'application/pdf',
        })
        self.pec.prescription_id.write({'message_main_attachment_id': presc_att.id})

        # PJ police
        policy_att = self.env['ir.attachment'].create({
            'name': 'carte_police.pdf',
            'type': 'binary',
            'datas': 'dGVzdA==',
            'res_model': 'optical.policy',
            'res_id': self.policy.id,
            'mimetype': 'application/pdf',
        })
        self.policy.write({'message_main_attachment_id': policy_att.id})

        result = self.pec.action_send_to_insurer()
        ctx = result['context']
        attachment_cmd = ctx['default_attachment_ids'][0]
        attachment_ids = attachment_cmd[2] if len(attachment_cmd) > 2 else []
        self.assertIn(presc_att.id, attachment_ids, "L'ordonnance doit etre dans les PJ")
        self.assertIn(policy_att.id, attachment_ids, "La carte police doit etre dans les PJ")

    def test_10_template_exists_after_install(self):
        """AC#7 : Le mail.template 'Demande de PEC' existe apres installation."""
        template = self.env.ref('optical.email_template_pec_request', raise_if_not_found=False)
        self.assertTrue(template, "Le mail.template 'Demande de PEC' doit exister")
        self.assertEqual(template.model, 'optical.pec')
        self.assertIn('object.insurer_id.id', template.partner_to)

    def test_11_template_body_simplified(self):
        """CC-2026-03-10 : Le corps du template est un courrier d'accompagnement concis."""
        template = self.env.ref('optical.email_template_pec_request')
        body = template.body_html
        self.assertIn('Bonjour', body)
        self.assertIn('prise en charge', body)
        self.assertIn('object.patient_id.name', body)
        self.assertIn('Cordialement', body)
        # Verifier absence des anciens tableaux detailles
        self.assertNotIn('<th', body, "Le template ne doit plus contenir de tableaux HTML")
