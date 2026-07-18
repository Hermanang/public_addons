# -*- coding: utf-8 -*-
import time
from datetime import date, timedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'optical_crm_followup')
class TestS01Consentement(TransactionCase):
    """Story 15.1 — Consentement, opt-out et fondations légales."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.group_optical_user = cls.env.ref('optical.group_optical_user')
        cls.group_optical_manager = cls.env.ref('optical.group_optical_manager')

        base_group = cls.env.ref('base.group_user').id
        partner_manager_group = cls.env.ref('base.group_partner_manager').id
        group_all_ou = cls.env.ref(
            'operating_unit_access_all.group_all_operating_unit',
            raise_if_not_found=False,
        )
        base_groups = [base_group, partner_manager_group]
        if group_all_ou:
            base_groups.append(group_all_ou.id)

        cls.warehouse = cls.env['stock.warehouse'].create({
            'name': 'Boutique Test S01',
            'code': 'S01',
        })

        cls.user_commercial = cls.env['res.users'].with_context(
            no_reset_password=True
        ).create({
            'name': 'Commercial S01',
            'login': 'commercial_s01',
            'email': 'commercial_s01@test.com',
            'groups_id': [Command.set([cls.group_optical_user.id] + base_groups)],
            'optical_warehouse_ids': [Command.set([cls.warehouse.id])],
        })
        cls.user_manager = cls.env['res.users'].with_context(
            no_reset_password=True
        ).create({
            'name': 'Manager S01',
            'login': 'manager_s01',
            'email': 'manager_s01@test.com',
            'groups_id': [Command.set([cls.group_optical_manager.id] + base_groups)],
        })

        cls.partner_adult = cls.env['res.partner'].create({
            'name': 'Client Majeur',
            'birthdate': date.today() - timedelta(days=int(30 * 365.25)),
        })
        cls.partner_minor = cls.env['res.partner'].create({
            'name': 'Client Mineur',
            'birthdate': date.today() - timedelta(days=int(15 * 365.25)),
        })
        cls.partner_no_bday = cls.env['res.partner'].create({
            'name': 'Client Sans Birthdate',
        })

        # Fixture ad-hoc : mail.template exemple consommant le footer légal
        # via <t t-call/>. Créée en test-only pour éviter la pollution du
        # catalogue mail en production.
        cls.demo_footer_template = cls.env['mail.template'].create({
            'name': 'Test S01 — Consommation footer légal',
            'model_id': cls.env['ir.model']._get('res.partner').id,
            'subject': 'Test footer légal',
            'body_html': (
                '<div>'
                '<p>Bonjour <t t-out="object.name or \'\'"/>,</p>'
                '<p>Exemple de corps utilisant le footer légal.</p>'
                '<t t-call="optical_crm_followup.mail_footer_legal"/>'
                '</div>'
            ),
        })

    # ------------------------------------------------------------------
    # AC1 — Consentement + chatter
    # ------------------------------------------------------------------

    def test_s01_consent_write_sets_date_and_user_and_posts_message(self):
        """AC1 — cocher consent renseigne date + user + post message chatter."""
        partner = self.partner_adult.with_user(self.user_commercial)
        msg_before = self.env['mail.message'].search_count(
            [('res_id', '=', partner.id), ('model', '=', 'res.partner')]
        )

        partner.write({'optical_followup_consent': True})

        self.assertTrue(partner.optical_followup_consent)
        self.assertEqual(partner.optical_followup_consent_date, fields.Date.today())
        self.assertEqual(
            partner.optical_followup_consent_by_id,
            self.user_commercial,
        )

        msgs = self.env['mail.message'].search([
            ('res_id', '=', partner.id),
            ('model', '=', 'res.partner'),
        ])
        self.assertEqual(len(msgs) - msg_before, 1)
        self.assertIn('Consentement de suivi enregistré', msgs[0].body)

    def test_s01_consent_recheck_updates_date_and_user_and_posts_second_message(self):
        """AC1 — décoche puis recoche : date + user à jour + 2ᵉ message chatter."""
        partner = self.partner_adult
        partner.with_user(self.user_commercial).write(
            {'optical_followup_consent': True}
        )
        # Décoche
        partner.with_user(self.user_manager).write(
            {'optical_followup_consent': False}
        )
        # Recoche par un autre utilisateur
        partner.with_user(self.user_manager).write(
            {'optical_followup_consent': True}
        )

        self.assertEqual(
            partner.optical_followup_consent_by_id,
            self.user_manager,
        )
        # 2 messages "Consentement de suivi enregistré" attendus
        msgs = self.env['mail.message'].search([
            ('res_id', '=', partner.id),
            ('model', '=', 'res.partner'),
            ('body', 'like', '%Consentement de suivi enregistré%'),
        ])
        self.assertGreaterEqual(len(msgs), 2)

    # ------------------------------------------------------------------
    # AC3 — Helper d'éligibilité
    # ------------------------------------------------------------------

    def test_s01_can_start_followup_no_consent(self):
        result, reason = self.partner_adult._can_start_followup()
        self.assertFalse(result)
        self.assertEqual(reason, 'no_consent')

    def test_s01_can_start_followup_optout(self):
        p = self.partner_adult
        p.write({'optical_followup_consent': True})
        p.write({'optical_followup_optout': True})
        result, reason = p._can_start_followup()
        self.assertFalse(result)
        self.assertEqual(reason, 'optout')

    def test_s01_can_start_followup_minor_no_legal_rep(self):
        p = self.partner_minor
        p.write({'optical_followup_consent': True})
        result, reason = p._can_start_followup()
        self.assertFalse(result)
        self.assertEqual(reason, 'minor_no_legal_rep')

    def test_s01_can_start_followup_minor_with_legal_rep(self):
        p = self.partner_minor
        p.write({
            'optical_followup_consent': True,
            'optical_followup_consent_by_legal_rep': True,
        })
        result, reason = p._can_start_followup()
        self.assertTrue(result)
        self.assertIsNone(reason)

    def test_s01_can_start_followup_adult_ok(self):
        p = self.partner_adult
        p.write({'optical_followup_consent': True})
        result, reason = p._can_start_followup()
        self.assertTrue(result)
        self.assertIsNone(reason)

    def test_s01_can_start_followup_no_birthdate_presumed_adult(self):
        p = self.partner_no_bday
        p.write({'optical_followup_consent': True})
        result, reason = p._can_start_followup()
        self.assertTrue(result)
        self.assertIsNone(reason)

    # ------------------------------------------------------------------
    # AC2 — Cascade opt-out + verrouillage
    # ------------------------------------------------------------------

    def _setup_running_schedule(self, partner):
        """Fixture : un schedule.running + 3 lignes pending, 2 avec activity_id."""
        schedule = self.env['optical.followup.schedule'].create({
            'name': 'SCH-S01-001',
            'partner_id': partner.id,
            'warehouse_id': self.warehouse.id,
            'state': 'running',
        })
        lines = self.env['optical.followup.schedule.line']
        model_partner = self.env['ir.model']._get('res.partner')
        activity_type = self.env.ref('mail.mail_activity_data_todo')
        for i in range(3):
            activity_id = False
            if i < 2:
                act = self.env['mail.activity'].create({
                    'res_model_id': model_partner.id,
                    'res_id': partner.id,
                    'activity_type_id': activity_type.id,
                    'summary': f'Rappel S01 #{i}',
                    'user_id': self.env.user.id,
                })
                activity_id = act.id
            lines |= self.env['optical.followup.schedule.line'].create({
                'schedule_id': schedule.id,
                'sequence': 10 * (i + 1),
                'state': 'pending',
                'activity_id': activity_id,
            })
        return schedule, lines

    def test_s01_optout_cascades_schedules_and_activities(self):
        """AC2 — coche opt-out : cascade schedule + lignes + activities < 60 s."""
        partner = self.partner_adult
        partner.write({'optical_followup_consent': True})
        schedule, lines = self._setup_running_schedule(partner)
        # Précondition : 2 activities existent
        act_ids_before = lines.mapped('activity_id').ids
        self.assertEqual(len(act_ids_before), 2)

        start = time.monotonic()
        partner.with_user(self.user_manager).write({
            'optical_followup_optout': True,
            'optical_followup_optout_reason': "Le client ne souhaite plus être contacté",
        })
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 60, "NFR-04 : cascade opt-out > 60 s")

        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'cancelled')
        for line in lines:
            line.invalidate_recordset()
            self.assertEqual(line.state, 'cancelled')

        # Activités supprimées
        remaining = self.env['mail.activity'].search(
            [('id', 'in', act_ids_before)]
        )
        self.assertFalse(remaining, "Les 2 mail.activity doivent être supprimées")

        # Chatter opt-out avec récapitulatif + raison (L3)
        msgs = self.env['mail.message'].search([
            ('res_id', '=', partner.id),
            ('model', '=', 'res.partner'),
            ('body', 'like', '%Opposition enregistrée%'),
        ])
        self.assertTrue(msgs)
        self.assertIn('1 calendrier(s) annulé(s)', msgs[0].body)
        self.assertIn('2 activité(s) pendante(s) supprimée(s)', msgs[0].body)
        self.assertIn(
            "Le client ne souhaite plus être contacté",
            msgs[0].body,
            "La raison doit apparaître dans le récapitulatif chatter",
        )

    def test_s01_optout_locks_future_creation(self):
        """AC2 — après opt-out, _can_start_followup renvoie False, 'optout'."""
        p = self.partner_adult
        p.write({'optical_followup_consent': True})
        p.write({'optical_followup_optout': True})
        result, reason = p._can_start_followup()
        self.assertFalse(result)
        self.assertEqual(reason, 'optout')

    def test_s01_optout_by_user_not_manager(self):
        """AC2 3ᵉ paragraphe — un user standard peut cocher opt-out."""
        partner = self.partner_adult
        partner.write({'optical_followup_consent': True})
        # User standard écrit sur partner (droit fondamental client)
        partner.with_user(self.user_commercial).write({
            'optical_followup_optout': True,
        })
        self.assertTrue(partner.optical_followup_optout)
        self.assertEqual(partner.optical_followup_optout_date, fields.Date.today())

    # ------------------------------------------------------------------
    # AC6 — Ancien client, pas de rétroactivité
    # ------------------------------------------------------------------

    def test_s01_consent_on_old_client_does_not_create_schedule(self):
        """AC6 — cocher consent sur un ancien client (avec SO+picking passés)
        ne crée aucun calendrier rétroactivement."""
        partner = self.env['res.partner'].create({'name': 'Ancien Client'})

        # Historique réel : SO confirmée → pickings générés (garantit qu'aucun
        # trigger sur res.partner.write ne "réveille" des SO passées).
        product = self.env['product.product'].search([], limit=1)
        if not product:
            product = self.env['product.product'].create({
                'name': 'Ancien Produit',
                'list_price': 100.0,
            })
        so = self.env['sale.order'].create({
            'partner_id': partner.id,
            'order_line': [Command.create({
                'product_id': product.id,
                'product_uom_qty': 1,
            })],
        })
        so.action_confirm()
        self.assertEqual(so.state, 'sale')
        self.assertTrue(so.picking_ids, "SO confirmée doit générer un picking")

        Schedule = self.env['optical.followup.schedule']
        count_before = Schedule.search_count([('partner_id', '=', partner.id)])

        partner.write({'optical_followup_consent': True})

        count_after = Schedule.search_count([('partner_id', '=', partner.id)])
        self.assertEqual(count_before, count_after)
        self.assertEqual(count_after, 0)

    # ------------------------------------------------------------------
    # AC4 — QWeb bon de commande contient le bloc consentement
    # ------------------------------------------------------------------

    def test_s01_qweb_report_contains_consent_block(self):
        """AC4 — le rendu du rapport sale.order contient la case de consentement."""
        product = self.env['product.product'].search([], limit=1)
        if not product:
            product = self.env['product.product'].create({
                'name': 'Produit S01',
                'list_price': 100.0,
            })
        so = self.env['sale.order'].create({
            'partner_id': self.partner_adult.id,
            'order_line': [Command.create({
                'product_id': product.id,
                'product_uom_qty': 1,
            })],
        })
        report_ref = 'sale.action_report_saleorder'
        report_service = self.env['ir.actions.report']._render_qweb_html(
            report_ref, so.ids,
        )
        html_bytes = report_service[0] if isinstance(report_service, tuple) else report_service
        html = html_bytes.decode('utf-8') if isinstance(html_bytes, bytes) else html_bytes
        self.assertIn("J'accepte de recevoir des messages de suivi", html)
        self.assertIn("représentant légal", html)

    # ------------------------------------------------------------------
    # AC5 — Template QWeb footer légal
    # ------------------------------------------------------------------

    def test_s01_mail_footer_legal_template_exists_and_renders(self):
        """AC5 — le template mail_footer_legal existe et rend la mention Loi 2008-12."""
        template_view = self.env.ref(
            'optical_crm_followup.mail_footer_legal',
            raise_if_not_found=False,
        )
        self.assertTrue(template_view, "Template QWeb mail_footer_legal absent")

        # Fixture ad-hoc (créée en setUpClass) qui consomme le footer via
        # <t t-call/>. Prouve que le template QWeb est appelable par les
        # mail.template livrés en aval (15.2, 16.1, 17.1).
        rendered = self.demo_footer_template._render_field(
            'body_html', [self.partner_adult.id]
        )
        body = rendered[self.partner_adult.id]
        self.assertIn("Loi n° 2008-12", body)

    # ------------------------------------------------------------------
    # Couverture régression post-review (H1, L2, M4)
    # ------------------------------------------------------------------

    def test_s01_optout_cascades_paused_schedule(self):
        """Régression H1 — cascade opt-out inclut aussi les calendriers ``paused``
        (SAV en cours) : sans quoi la reprise SAV ré-activerait un dispositif
        sur un client désormais opt-out (FR-08 : verrouillage total)."""
        partner = self.partner_adult
        partner.write({'optical_followup_consent': True})
        schedule = self.env['optical.followup.schedule'].create({
            'name': 'SCH-S01-PAUSED',
            'partner_id': partner.id,
            'warehouse_id': self.warehouse.id,
            'state': 'paused',
        })
        model_partner = self.env['ir.model']._get('res.partner')
        activity_type = self.env.ref('mail.mail_activity_data_todo')
        act = self.env['mail.activity'].create({
            'res_model_id': model_partner.id,
            'res_id': partner.id,
            'activity_type_id': activity_type.id,
            'summary': 'Rappel S01 pause',
            'user_id': self.env.user.id,
        })
        line_paused = self.env['optical.followup.schedule.line'].create({
            'schedule_id': schedule.id,
            'sequence': 10,
            'state': 'paused',
            'activity_id': act.id,
        })

        partner.with_user(self.user_manager).write({
            'optical_followup_optout': True,
            'optical_followup_optout_reason': "SAV — refus post-livraison",
        })

        schedule.invalidate_recordset()
        line_paused.invalidate_recordset()
        self.assertEqual(schedule.state, 'cancelled')
        self.assertEqual(line_paused.state, 'cancelled')
        self.assertFalse(
            self.env['mail.activity'].search([('id', '=', act.id)]),
            "L'activité de la ligne paused doit être supprimée",
        )

    def test_s01_optout_cascades_overdue_lines(self):
        """Régression L2 — cascade opt-out couvre également les lignes en
        ``state='overdue'`` (le code inclut le cas mais aucun test ne
        l'exerçait)."""
        partner = self.partner_adult
        partner.write({'optical_followup_consent': True})
        schedule = self.env['optical.followup.schedule'].create({
            'name': 'SCH-S01-OVERDUE',
            'partner_id': partner.id,
            'warehouse_id': self.warehouse.id,
            'state': 'running',
        })
        model_partner = self.env['ir.model']._get('res.partner')
        activity_type = self.env.ref('mail.mail_activity_data_todo')
        act = self.env['mail.activity'].create({
            'res_model_id': model_partner.id,
            'res_id': partner.id,
            'activity_type_id': activity_type.id,
            'summary': 'Rappel S01 overdue',
            'user_id': self.env.user.id,
        })
        line_overdue = self.env['optical.followup.schedule.line'].create({
            'schedule_id': schedule.id,
            'sequence': 10,
            'state': 'overdue',
            'activity_id': act.id,
        })

        partner.write({'optical_followup_optout': True})

        line_overdue.invalidate_recordset()
        self.assertEqual(line_overdue.state, 'cancelled')
        self.assertFalse(
            self.env['mail.activity'].search([('id', '=', act.id)]),
            "L'activité de la ligne overdue doit être supprimée",
        )

    def test_s01_consent_date_cannot_be_backdated_via_write(self):
        """Régression M4 — l'horodatage consent est audit CDP : un caller
        NE DOIT PAS pouvoir antidater en passant sa propre date dans vals.
        L'override force la date du jour."""
        partner = self.partner_adult
        forged_date = date.today() - timedelta(days=365 * 2)  # 2 ans en arrière
        partner.with_user(self.user_commercial).write({
            'optical_followup_consent': True,
            'optical_followup_consent_date': forged_date,
        })
        self.assertEqual(
            partner.optical_followup_consent_date,
            fields.Date.today(),
            "L'auto-timestamp doit écraser toute date fournie par le caller",
        )

    def test_s01_optout_date_cannot_be_backdated_via_write(self):
        """Régression M4 — idem sur l'horodatage opt-out."""
        partner = self.partner_adult
        partner.write({'optical_followup_consent': True})
        forged_date = date.today() - timedelta(days=90)
        partner.with_user(self.user_manager).write({
            'optical_followup_optout': True,
            'optical_followup_optout_date': forged_date,
        })
        self.assertEqual(
            partner.optical_followup_optout_date,
            fields.Date.today(),
            "L'auto-timestamp optout doit écraser toute date fournie",
        )
