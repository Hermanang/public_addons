# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestOpticalHelpdesk(TransactionCase):
    """Tests du module optical_helpdesk : sequence type-aware, motifs m2m,
    rapport, purchase_price compute."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Client Test Helpdesk',
            'phone': '77 000 11 22',
            'customer_rank': 1,
        })
        cls.team = cls.env['helpdesk.ticket.team'].create({
            'name': 'Equipe Test Helpdesk',
        })
        cls.type_complaint = cls.env.ref('optical_helpdesk.type_complaint')
        cls.type_sav = cls.env.ref('optical_helpdesk.type_sav')
        cls.type_inquiry = cls.env.ref('optical_helpdesk.type_inquiry')
        cls.cat_optique_verres = cls.env.ref('optical_helpdesk.category_optique_verres')
        cls.motive_verre_raye = cls.env.ref('optical_helpdesk.motive_verre_raye')
        cls.motive_charniere = cls.env.ref('optical_helpdesk.motive_charniere_desserree')

    # ========== Sequence ==========

    def test_sequence_complaint_uses_TR_prefix(self):
        ticket = self.env['helpdesk.ticket'].create({
            'name': 'Test seq complaint',
            'partner_id': self.partner.id,
            'team_id': self.team.id,
            'type_id': self.type_complaint.id,
            'description': '<p>x</p>',
        })
        self.assertTrue(ticket.number.startswith('TR'),
                        f"Expected TR prefix, got {ticket.number}")

    def test_sequence_sav_uses_native_HT_prefix(self):
        ticket = self.env['helpdesk.ticket'].create({
            'name': 'Test seq SAV',
            'partner_id': self.partner.id,
            'team_id': self.team.id,
            'type_id': self.type_sav.id,
            'description': '<p>x</p>',
        })
        self.assertTrue(ticket.number.startswith('HT'),
                        f"Expected HT prefix, got {ticket.number}")

    def test_sequence_inquiry_uses_native_HT_prefix(self):
        ticket = self.env['helpdesk.ticket'].create({
            'name': 'Test seq inquiry',
            'partner_id': self.partner.id,
            'team_id': self.team.id,
            'type_id': self.type_inquiry.id,
            'description': '<p>x</p>',
        })
        self.assertTrue(ticket.number.startswith('HT'),
                        f"Expected HT prefix, got {ticket.number}")

    # ========== Motifs reclamation (m2m custom) ==========

    def test_complaint_motive_multi_select(self):
        """Plusieurs motifs peuvent etre attaches a un meme ticket Reclamation."""
        ticket = self.env['helpdesk.ticket'].create({
            'name': 'Test multi motifs',
            'partner_id': self.partner.id,
            'team_id': self.team.id,
            'type_id': self.type_complaint.id,
            'complaint_motive_ids': [(6, 0, [
                self.motive_verre_raye.id,
                self.motive_charniere.id,
            ])],
            'description': '<p>x</p>',
        })
        self.assertEqual(len(ticket.complaint_motive_ids), 2)
        self.assertIn(self.motive_verre_raye, ticket.complaint_motive_ids)
        self.assertIn(self.motive_charniere, ticket.complaint_motive_ids)

    # ========== Rapport QWeb ==========

    def test_report_action_domain_filters_complaint_only(self):
        from ast import literal_eval
        report = self.env.ref('optical_helpdesk.action_report_complaint_ticket')
        domain = literal_eval(report.domain)
        self.assertEqual(domain, [('type_id', '=', self.type_complaint.id)])

    def test_report_renders_for_complaint(self):
        """Le template QWeb se rend sans exception et produit un contenu
        substantiel (> 5000 bytes pour distinguer un vrai rendu d'un HTML
        d'erreur ou d'un PDF vide). En mode test Odoo retourne souvent
        HTML au lieu de PDF (perf), on accepte les deux mais on valide
        le contenu."""
        ticket = self.env['helpdesk.ticket'].create({
            'name': 'Test PDF',
            'partner_id': self.partner.id,
            'partner_phone': '77 000 11 22',
            'team_id': self.team.id,
            'type_id': self.type_complaint.id,
            'category_id': self.cat_optique_verres.id,
            'complaint_motive_ids': [(6, 0, [self.motive_verre_raye.id])],
            'cause_identified': 'fournisseur',
            'proposed_solution': 'remplacement_verre',
            'description': '<p>Description test</p>',
            'internal_diagnostic': '<p>Diagnostic test</p>',
        })
        report = self.env.ref('optical_helpdesk.action_report_complaint_ticket')
        content, content_type = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
            report.report_name, [ticket.id],
        )
        self.assertIn(content_type, ('pdf', 'html'),
                      f"Type inattendu : {content_type}")
        # 5000 bytes minimum : HTML de Odoo plus la structure complète du
        # rapport (header, 2 volets, sections, etc.) doit dépasser 5KB.
        # Si on est sous ce seuil, le template a probablement échoué silencieusement.
        self.assertGreater(len(content), 5000,
                           f"Contenu trop petit ({len(content)} bytes), "
                           f"probablement template incomplet ou erreur silencieuse")
        if content_type == 'pdf':
            self.assertTrue(content.startswith(b'%PDF'),
                            "Le contenu PDF ne commence pas par %PDF")

    def test_report_robust_to_missing_motive(self):
        """Si un motif est supprimé via UI, le rapport ne crashe pas
        (regression : env.ref sans raise_if_not_found=False crashait).
        """
        # Crée un ticket avec un motif puis supprime le motif
        custom_motive = self.env['helpdesk.complaint.motive'].create({
            'name': 'Custom motive test',
        })
        ticket = self.env['helpdesk.ticket'].create({
            'name': 'Test motive deletion',
            'partner_id': self.partner.id,
            'team_id': self.team.id,
            'type_id': self.type_complaint.id,
            'category_id': self.cat_optique_verres.id,
            'complaint_motive_ids': [(6, 0, [custom_motive.id])],
            'description': '<p>x</p>',
        })
        # Supprime un motif seedé pour vérifier que le rapport survit
        # (le rapport référence motive_oxydation_metal par xmlid)
        oxydation = self.env.ref(
            'optical_helpdesk.motive_oxydation_metal',
            raise_if_not_found=False,
        )
        if oxydation:
            oxydation.unlink()
        # Le rapport doit toujours se rendre
        report = self.env.ref('optical_helpdesk.action_report_complaint_ticket')
        content, _ct = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
            report.report_name, [ticket.id],
        )
        self.assertGreater(len(content), 5000,
                           "Le rapport a échoué silencieusement après suppression d'un motif seedé")

    # ========== M1 : sanity demo data + xml_ids ==========

    def test_demo_xml_ids_resolve(self):
        """Les xml_ids référencés dans le demo file et le rapport QWeb
        existent en DB après installation. Catch les ruptures silencieuses
        si un record seedé est renommé/supprimé sans cleanup des refs."""
        critical_xmlids = [
            # Types
            'optical_helpdesk.type_complaint',
            'optical_helpdesk.type_sav',
            'optical_helpdesk.type_inquiry',
            # Categories utilisées en demo
            'optical_helpdesk.category_optique',
            'optical_helpdesk.category_optique_verres',
            'optical_helpdesk.category_optique_montures',
            'optical_helpdesk.category_optique_lentilles',
            'optical_helpdesk.category_service',
            'optical_helpdesk.category_service_tarif',
            'optical_helpdesk.category_service_mutuelle',
            # Motifs référencés par le rapport QWeb
            'optical_helpdesk.motive_defaut_fabrication',
            'optical_helpdesk.motive_erreur_correction',
            'optical_helpdesk.motive_probleme_reglage',
            'optical_helpdesk.motive_verre_raye',
            'optical_helpdesk.motive_charniere_desserree',
            'optical_helpdesk.motive_inconfort_visuel',
            'optical_helpdesk.motive_retard_livraison',
            'optical_helpdesk.motive_verre_casse',
            'optical_helpdesk.motive_branches_cassees',
            'optical_helpdesk.motive_pont_casse',
            'optical_helpdesk.motive_alteration_matiere',
            'optical_helpdesk.motive_fixation_plaquettes',
            'optical_helpdesk.motive_oxydation_metal',
            'optical_helpdesk.motive_autre',
            # Action rapport + paperformat
            'optical_helpdesk.action_report_complaint_ticket',
            'optical_helpdesk.paperformat_optical_complaint_a5',
        ]
        for xmlid in critical_xmlids:
            self.assertTrue(
                self.env.ref(xmlid, raise_if_not_found=False),
                f"xmlid critique non résolu : {xmlid}",
            )

    # ========== purchase_price compute ==========

    def test_purchase_price_compute_from_sale_order_line(self):
        product = self.env['product.product'].create({
            'name': 'Test Verre',
            'type': 'consu',
            'list_price': 50000,
            'sale_ok': True,
        })
        so = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': product.id,
                'product_uom_qty': 1,
                'price_unit': 50000,
            })],
        })
        ticket = self.env['helpdesk.ticket'].create({
            'name': 'Test prix',
            'partner_id': self.partner.id,
            'team_id': self.team.id,
            'type_id': self.type_complaint.id,
            'sale_order_ids': [(6, 0, [so.id])],
            'product_id': product.id,
            'description': '<p>x</p>',
        })
        self.assertGreater(ticket.purchase_price, 0,
                           "purchase_price doit etre calcule depuis la SO")
