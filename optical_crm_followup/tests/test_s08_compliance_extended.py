# -*- coding: utf-8 -*-
"""Story 17-3 AC-A + AC-B + AC-D — tests compliance étendue.

Couvre :
- AC-A : majorité 18 ans (mail J+18, pause J+90, bouton confirmation)
- AC-B : anonymisation cyclique (cron mensuel, éligibilité, write-once)
- AC-D : rapport droit d'accès CDP (PDF, chatter, rejet company)
"""
from datetime import date, timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'optical_crm_followup')
class TestS08ComplianceExtended(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.group_optical_user = cls.env.ref('optical.group_optical_user')
        cls.group_optical_manager = cls.env.ref('optical.group_optical_manager')

        base_group = cls.env.ref('base.group_user').id
        partner_manager = cls.env.ref('base.group_partner_manager').id
        stock_manager = cls.env.ref('stock.group_stock_manager').id
        sales_manager = cls.env.ref('sales_team.group_sale_manager').id
        group_all_ou = cls.env.ref(
            'operating_unit_access_all.group_all_operating_unit',
            raise_if_not_found=False,
        )
        cls.base_groups = [base_group, partner_manager, stock_manager, sales_manager]
        if group_all_ou:
            cls.base_groups.append(group_all_ou.id)

        cls.warehouse = cls.env['stock.warehouse'].create({
            'name': 'Boutique S08',
            'code': 'S08',
        })

        cls.user_manager = cls.env['res.users'].with_context(
            no_reset_password=True,
        ).create({
            'name': 'Manager S08',
            'login': 'manager_s08',
            'email': 'manager_s08@test.com',
            'groups_id': [Command.set([cls.group_optical_manager.id] + cls.base_groups)],
        })
        cls.user_commercial = cls.env['res.users'].with_context(
            no_reset_password=True,
        ).create({
            'name': 'Commercial S08',
            'login': 'commercial_s08',
            'email': 'commercial_s08@test.com',
            'groups_id': [Command.set([cls.group_optical_user.id] + cls.base_groups)],
            'optical_warehouse_ids': [Command.set([cls.warehouse.id])],
        })

        cls.plan_std18m = cls.env.ref('optical_crm_followup.plan_standard_18m')

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_partner(self, name='Client S08', **kwargs):
        vals = {'name': name, 'is_company': False}
        vals.update(kwargs)
        return self.env['res.partner'].create(vals)

    def _create_schedule_direct(self, partner, state='running', pause_reason=False):
        schedule = self.env['optical.followup.schedule'].sudo().create({
            'name': 'SUIVI-S08-%s' % partner.id,
            'partner_id': partner.id,
            'warehouse_id': self.warehouse.id,
            'plan_id': self.plan_std18m.id,
            'state': state,
            'pause_reason': pause_reason or False,
            'referent_user_id': self.user_commercial.id,
        })
        # Créer une ligne pending pour simuler un schedule actif
        line_state = 'paused' if state == 'paused' else 'pending'
        self.env['optical.followup.schedule.line'].sudo().create({
            'schedule_id': schedule.id,
            'sequence': 10,
            'date_planned': fields.Date.today() + timedelta(days=30),
            'date_planned_original': fields.Date.today() + timedelta(days=30),
            'state': line_state,
        })
        return schedule

    # ==================================================================
    # AC-A — Majorité (mail, pause, bouton)
    # ==================================================================

    def test_ac_a_majority_scheduled_action_sets_request_date(self):
        """Cron RH — mail envoyé + date posée si birthdate + 18 ans <= today."""
        birthdate = fields.Date.today() - timedelta(days=int(18 * 365.25 + 5))
        partner = self._create_partner(
            name='Client Majeur S08',
            email='majeur_s08@test.com',
            birthdate=birthdate,
            optical_followup_consent=True,
            optical_followup_consent_by_legal_rep=True,
        )
        self._create_schedule_direct(partner, state='running')

        self.env['optical.followup.schedule']._process_majority_transitions()

        self.assertEqual(
            partner.optical_followup_majority_request_date,
            fields.Date.today(),
        )

    def test_ac_a_majority_pause_after_90d(self):
        """Cron RH — schedule pauseé après 90 j sans confirmation."""
        partner = self._create_partner(
            name='Client Majeur Sans Réponse',
            email='sans_reponse@test.com',
            optical_followup_consent=True,
            optical_followup_consent_by_legal_rep=True,
        )
        # Simule que le mail a été envoyé il y a 91 j
        past_date = fields.Date.today() - timedelta(days=91)
        partner.sudo().write({
            'optical_followup_majority_request_date': past_date,
        })
        schedule = self._create_schedule_direct(partner, state='running')

        self.env['optical.followup.schedule']._process_majority_transitions()

        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'paused')
        self.assertEqual(schedule.pause_reason, 'majority_pending')

    def test_ac_a_majority_pause_idempotent_on_sav_paused(self):
        """Un schedule paused SAV n'est PAS re-écrit par pause majorité."""
        partner = self._create_partner(
            name='Client Majeur SAV',
            email='sav_majeur@test.com',
            optical_followup_consent=True,
            optical_followup_consent_by_legal_rep=True,
        )
        past_date = fields.Date.today() - timedelta(days=91)
        partner.sudo().write({
            'optical_followup_majority_request_date': past_date,
        })
        schedule = self._create_schedule_direct(
            partner, state='paused', pause_reason='sav_open',
        )
        schedule.sudo().write({'sav_paused_date': fields.Date.today() - timedelta(days=30)})

        self.env['optical.followup.schedule']._process_majority_transitions()

        schedule.invalidate_recordset()
        # SAV inchangé
        self.assertEqual(schedule.state, 'paused')
        self.assertEqual(schedule.pause_reason, 'sav_open')

    def test_ac_a_confirm_majority_reactivates_schedule(self):
        """Bouton manager — schedule paused/majority_pending → running."""
        partner = self._create_partner(
            name='Client Majeur À Confirmer',
            email='confirmer@test.com',
            optical_followup_consent=True,
            optical_followup_consent_by_legal_rep=True,
        )
        partner.sudo().write({
            'optical_followup_majority_request_date': fields.Date.today() - timedelta(days=30),
        })
        schedule = self._create_schedule_direct(
            partner, state='paused', pause_reason='majority_pending',
        )

        partner.with_user(self.user_manager).action_optical_followup_confirm_majority()

        schedule.invalidate_recordset()
        partner.invalidate_recordset()
        self.assertEqual(schedule.state, 'running')
        self.assertFalse(schedule.pause_reason)
        self.assertFalse(partner.optical_followup_consent_by_legal_rep)
        self.assertTrue(partner.optical_followup_consent)
        # majority_request_date CONSERVÉ (audit — write-once soft)
        self.assertTrue(partner.optical_followup_majority_request_date)

    def test_ac_a_confirm_majority_does_not_reactivate_sav_paused(self):
        """Garde-fou : bouton ne touche pas schedules paused/sav_open."""
        partner = self._create_partner(
            name='Client Majeur SAV Confirm',
            email='sav_confirm@test.com',
            optical_followup_consent=True,
            optical_followup_consent_by_legal_rep=True,
        )
        partner.sudo().write({
            'optical_followup_majority_request_date': fields.Date.today() - timedelta(days=30),
        })
        schedule = self._create_schedule_direct(
            partner, state='paused', pause_reason='sav_open',
        )

        partner.with_user(self.user_manager).action_optical_followup_confirm_majority()

        schedule.invalidate_recordset()
        # SAV inchangé
        self.assertEqual(schedule.state, 'paused')
        self.assertEqual(schedule.pause_reason, 'sav_open')

    def test_ac_a_confirm_majority_requires_manager(self):
        """AccessError si non-manager appelle l'action."""
        partner = self._create_partner(
            name='Client Majeur ACL',
            optical_followup_consent=True,
            optical_followup_consent_by_legal_rep=True,
        )
        partner.sudo().write({
            'optical_followup_majority_request_date': fields.Date.today() - timedelta(days=30),
        })
        with self.assertRaises(AccessError):
            partner.with_user(self.user_commercial).action_optical_followup_confirm_majority()

    # ==================================================================
    # AC-B — Anonymisation
    # ==================================================================

    def test_ac_b_anonymize_selects_optout_12m(self):
        """Éligibilité (a) : partner opt-out > 12 mois."""
        partner = self._create_partner(
            name='Client Optout Ancien',
            optical_followup_consent=True,
        )
        # Passage optout=True — l'override write S15.1 pose optout_date=today
        partner.sudo().write({'optical_followup_optout': True})
        # Écrire une date ancienne dans un 2ᵉ write (pas de bascule optout,
        # pas d'override auto-timestamp) — pattern de bypass en test
        partner.sudo().write({
            'optical_followup_optout_date': fields.Date.today() - timedelta(days=400),
        })
        candidates = self.env['res.partner']._anonymize_get_candidates()
        self.assertIn(partner, candidates)

    def test_ac_b_anonymize_skips_recent_optout(self):
        """Partner opt-out < 12 mois : non éligible."""
        partner = self._create_partner(name='Client Optout Récent')
        partner.sudo().write({
            'optical_followup_optout': True,
            'optical_followup_optout_date': fields.Date.today() - timedelta(days=100),
        })
        candidates = self.env['res.partner']._anonymize_get_candidates()
        self.assertNotIn(partner, candidates)

    def test_ac_b_anonymize_skips_companies(self):
        """Personnes morales exclues de l'anonymisation."""
        partner = self._create_partner(
            name='Société Optout',
            is_company=True,
        )
        partner.sudo().write({
            'optical_followup_optout': True,
            'optical_followup_optout_date': fields.Date.today() - timedelta(days=400),
        })
        candidates = self.env['res.partner']._anonymize_get_candidates()
        self.assertNotIn(partner, candidates)

    def test_ac_b_anonymize_wipes_pii(self):
        """PII effacées + name → 'Client anonymisé #<id>' + flag posé."""
        partner = self._create_partner(
            name='Client À Anonymiser',
            email='wipe@test.com',
            phone='+221 33 000 00 00',
            street='Rue Test',
            optical_followup_consent=True,
        )
        partner._anonymize_for_followup(reason='inactive_5y')
        partner.invalidate_recordset()
        self.assertTrue(partner.optical_anonymized)
        self.assertEqual(partner.optical_anonymized_date, fields.Date.today())
        self.assertEqual(partner.name, "Client anonymisé #%d" % partner.id)
        self.assertFalse(partner.email)
        self.assertFalse(partner.phone)
        self.assertFalse(partner.street)
        self.assertFalse(partner.optical_followup_consent)

    def test_ac_b_anonymize_is_write_once(self):
        """UserError si write non-whitelisté sur partner anonymisé (env.su=False)."""
        partner = self._create_partner(name='Anon À Verrouiller')
        partner._anonymize_for_followup(reason='inactive_5y')
        # env.su=True (superuser + admin) bypass le check — en test on doit
        # forcer un contexte non-sudo. with_user() sur un manager crée un
        # env non-superuser mais avec les droits ACL nécessaires.
        with self.assertRaises(UserError):
            partner.with_user(self.user_manager).write({'email': 'bypass@test.com'})

    def test_ac_b_anonymize_write_allows_whitelisted(self):
        """parent_id et active restent modifiables (whitelist)."""
        partner = self._create_partner(name='Anon Whitelist')
        partner._anonymize_for_followup(reason='inactive_5y')
        # active = False doit passer
        partner.write({'active': False})
        self.assertFalse(partner.active)

    def test_ac_b_anonymize_cascade_cancels_schedules(self):
        """Schedules running/paused du partner → cancelled + activités unlinked."""
        partner = self._create_partner(
            name='Anon Avec Schedule',
            optical_followup_consent=True,
        )
        schedule = self._create_schedule_direct(partner, state='running')
        # Créer aussi une activité liée
        activity = self.env['mail.activity'].sudo().create({
            'res_model': 'res.partner',
            'res_model_id': self.env['ir.model']._get('res.partner').id,
            'res_id': partner.id,
            'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
            'user_id': self.user_commercial.id,
            'summary': 'Test S08 anonym',
            'date_deadline': fields.Date.today(),
        })
        # Rattacher l'activité à la ligne
        schedule.line_ids[:1].sudo().write({'activity_id': activity.id})

        partner._anonymize_for_followup(reason='inactive_5y')

        schedule.invalidate_recordset()
        self.assertEqual(schedule.state, 'cancelled')
        # Activité unlinked
        self.assertFalse(activity.exists())

    def test_ac_b_anonymize_dry_run_no_side_effects(self):
        """_anonymize_dry_run retourne count sans modifier."""
        partner = self._create_partner(
            name='Dry Run',
            optical_followup_consent=True,
        )
        partner.sudo().write({'optical_followup_optout': True})
        partner.sudo().write({
            'optical_followup_optout_date': fields.Date.today() - timedelta(days=400),
        })
        count, records = self.env['res.partner']._anonymize_dry_run()
        partner.invalidate_recordset()
        self.assertIn(partner, records)
        self.assertFalse(partner.optical_anonymized)

    # ==================================================================
    # AC-D — Extrait droit d'accès
    # ==================================================================

    def test_ac_d_data_export_rejects_company(self):
        """Personne morale → warning dict sans exception."""
        company_partner = self._create_partner(
            name='Société Test S08',
            is_company=True,
        )
        result = company_partner.with_user(
            self.user_manager,
        ).action_optical_followup_data_export()
        self.assertIn('warning', result)

    def test_ac_d_data_export_generates_pdf(self):
        """Personne physique → contenu non vide (pdf ou html en test env)."""
        partner = self._create_partner(
            name='Client Data Export',
            email='export@test.com',
            optical_followup_consent=True,
        )
        report = self.env.ref(
            'optical_crm_followup.action_report_partner_data_export',
        )
        # with_user(manager) : le garde-fou AbstractModel `_get_report_values`
        # vérifie que l'utilisateur courant est manager (revue S17-3 H2).
        content, content_type = report.with_user(
            self.user_manager,
        )._render_qweb_pdf(
            'optical_crm_followup.action_report_partner_data_export',
            [partner.id],
        )
        # En test env, wkhtmltopdf peut retourner html si non convertible —
        # l'important est que le rendu QWeb ne lève pas d'erreur.
        self.assertTrue(content)
        self.assertIn(content_type, ('pdf', 'html'))

    def test_ac_d_data_export_url_blocked_for_non_manager(self):
        """H2 — le rapport doit lever AccessError si un non-manager
        appelle _render_qweb_pdf (simulation de l'accès URL direct)."""
        from odoo.exceptions import AccessError
        partner = self._create_partner(
            name='Client Data Export URL Guard',
            email='urlblock@test.com',
        )
        report = self.env.ref(
            'optical_crm_followup.action_report_partner_data_export',
        )
        with self.assertRaises(AccessError):
            report.with_user(self.user_commercial)._render_qweb_pdf(
                'optical_crm_followup.action_report_partner_data_export',
                [partner.id],
            )

    def test_ac_d_data_export_posts_pdf_on_chatter(self):
        """L'action de server pose une PJ PDF sur le chatter partner."""
        partner = self._create_partner(
            name='Client Data Export Chatter',
            email='chatter_export@test.com',
        )
        partner.with_user(self.user_manager).action_optical_followup_data_export()
        attachments = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'res.partner'),
            ('res_id', '=', partner.id),
            ('mimetype', '=', 'application/pdf'),
        ])
        self.assertTrue(attachments)

    # ==================================================================
    # Revue adversariale S17-3 — findings additionnels
    # ==================================================================

    def test_ac_a_no_email_creates_warning_activity(self):
        """AC-A.1 branche « pas d'email » : warning + activité manager (M1)."""
        birthdate = fields.Date.today() - timedelta(days=int(18 * 365.25 + 5))
        partner = self._create_partner(
            name='Client Majeur Sans Email',
            email=False,
            birthdate=birthdate,
            optical_followup_consent=True,
            optical_followup_consent_by_legal_rep=True,
        )
        self._create_schedule_direct(partner, state='running')
        # Il faut au moins une SO pour que _resolve_late_alert_manager
        # trouve la boutique et le manager
        self.env['sale.order'].sudo().create({
            'partner_id': partner.id,
            'user_id': self.user_commercial.id,
            'warehouse_id': self.warehouse.id,
            'state': 'sale',
            'date_order': fields.Datetime.now(),
        })
        self.env['optical.followup.schedule']._process_majority_transitions()

        # Pas de date posée (mail non envoyé) mais activité warning créée
        partner.invalidate_recordset()
        self.assertFalse(partner.optical_followup_majority_request_date)
        activities = self.env['mail.activity'].sudo().search([
            ('res_model', '=', 'sale.order'),
            ('summary', 'ilike', 'sans email'),
        ])
        self.assertTrue(activities, "Une activité warning devrait être créée")

    def test_ac_b_anonymize_selects_inactive_5y(self):
        """Éligibilité (b) : dernière SO > 5 ans → partner éligible (M2)."""
        partner = self._create_partner(name='Client Inactif 5y')
        # Créer une vieille SO
        old_date = fields.Datetime.now() - timedelta(days=365 * 5 + 30)
        self.env['sale.order'].sudo().create({
            'partner_id': partner.id,
            'user_id': self.user_commercial.id,
            'warehouse_id': self.warehouse.id,
            'state': 'sale',
            'date_order': old_date,
        })
        candidates = self.env['res.partner']._anonymize_get_candidates()
        self.assertIn(partner, candidates)

    def test_ac_b_anonymize_write_inline_flag_blocked(self):
        """M7 — bascule inline optical_anonymized=True + autres champs bloquée."""
        partner = self._create_partner(name='Client Bypass Attempt')
        with self.assertRaises(UserError):
            partner.with_user(self.user_manager).write({
                'optical_anonymized': True,
                'email': 'bypass@test.com',
            })

    def test_ac_a_majority_write_once_mixed_batch(self):
        """H3 — batch mixte : partner déjà daté n'est PAS écrasé."""
        partner_a = self._create_partner(name='Batch A daté')
        partner_b = self._create_partner(name='Batch B non daté')
        first_date = fields.Date.today() - timedelta(days=30)
        # Poser la date sur A uniquement (sudo pour bypass du soft check)
        partner_a.sudo().write({
            'optical_followup_majority_request_date': first_date,
        })
        # Ecriture mixte non-sudo — B doit être posé, A doit rester à first_date
        (partner_a + partner_b).with_user(self.user_manager).write({
            'optical_followup_majority_request_date': fields.Date.today(),
        })
        partner_a.invalidate_recordset()
        partner_b.invalidate_recordset()
        self.assertEqual(partner_a.optical_followup_majority_request_date, first_date)
        self.assertEqual(
            partner_b.optical_followup_majority_request_date, fields.Date.today(),
        )
