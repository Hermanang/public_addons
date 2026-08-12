# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .common import OpticalTestCommon


@tagged('post_install', '-at_install')
class TestSaleOrderLineSnapshotStory19_5(OpticalTestCommon):
    """Tests dédiés Story 19-5 : snapshot caractéristiques verre + eye_side + verrouillage post-confirmation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Référentiels
        cls.index_160 = cls.env['optical.lens.index'].create({'name': '1.60 Test S19-5', 'value': 1.60})
        cls.index_167 = cls.env['optical.lens.index'].create({'name': '1.67 Test S19-5', 'value': 1.67})
        cls.thickness_aminci = cls.env['optical.lens.thickness'].create({'name': 'Aminci Test S19-5'})
        cls.thickness_ultra = cls.env['optical.lens.thickness'].create({'name': 'Ultra-aminci Test S19-5'})
        cls.treatment_ar = cls.env['optical.lens.treatment'].create({
            'name': 'Antireflet Test S19-5',
            'treatment_type': 'complement',
        })
        cls.treatment_photo = cls.env['optical.lens.treatment'].create({
            'name': 'Photochromique Test S19-5',
            'treatment_type': 'base',
        })
        cls.tint_blanc = cls.env['optical.lens.tint'].create({'name': 'Blanc Test S19-5'})
        cls.brand_essilor = cls.env['product.brand'].create({'name': 'Essilor Test S19-5'})
        cls.brand_zeiss = cls.env['product.brand'].create({'name': 'Zeiss Test S19-5'})

        # Produits typés
        cls.product_lens = cls.env['product.product'].create({
            'name': 'Verre Test S19-5',
            'type': 'consu',
            'list_price': 30000.0,
            'taxes_id': [],
            'optical_type': 'lens',
        })
        cls.product_accessory = cls.env['product.product'].create({
            'name': 'Accessoire Test S19-5',
            'type': 'consu',
            'list_price': 500.0,
            'taxes_id': [],
            'optical_type': 'accessory',
        })
        cls.product_frame = cls.env['product.product'].create({
            'name': 'Monture Test S19-5',
            'type': 'consu',
            'list_price': 50000.0,
            'taxes_id': [],
            'optical_type': 'frame',
        })
        cls.product_contact = cls.env['product.product'].create({
            'name': 'Lentille Test S19-5',
            'type': 'consu',
            'list_price': 5000.0,
            'taxes_id': [],
            'optical_type': 'contact_lens',
        })

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _make_confirmed_lens_order(self, eye='od'):
        """Crée une SO avec 1 ligne verre + eye_side, la confirme.

        Créée comme le vendeur pour que celui-ci ait les droits record-rule
        de write() dans les tests aval (sinon on obtiendrait un AccessError
        de record-rules avant même d'atteindre notre override write()).
        """
        order = self.env['sale.order'].with_user(self.user_vendeur).create({
            'partner_id': self.patient.id,
            'order_line': [Command.create({
                'product_id': self.product_lens.id,
                'product_uom_qty': 1,
                'eye_side': eye,
                'lens_index_ordered_id': self.index_160.id,
                'lens_thickness_ordered_id': self.thickness_aminci.id,
            })],
        })
        order.action_confirm()
        return order, order.order_line

    # ------------------------------------------------------------------
    # Bloc A — Définition champs (AC-1) : 3 tests
    # ------------------------------------------------------------------

    def test_snapshot_fields_defined(self):
        """AC-1.2 + AC-1.3 : les 11 champs (eye_side + 10 snapshot) sont définis avec les bons types/comodels."""
        SOL = self.env['sale.order.line']
        # eye_side
        self.assertEqual(SOL._fields['eye_side'].type, 'selection')
        self.assertEqual(
            SOL._fields['eye_side'].selection,
            [('od', 'OD'), ('og', 'OG')],
        )
        self.assertFalse(SOL._fields['eye_side'].required)
        # M2O
        for fname, comodel in [
            ('lens_index_ordered_id', 'optical.lens.index'),
            ('lens_thickness_ordered_id', 'optical.lens.thickness'),
            ('lens_brand_ordered_id', 'product.brand'),
        ]:
            with self.subTest(field=fname):
                self.assertEqual(SOL._fields[fname].type, 'many2one')
                self.assertEqual(SOL._fields[fname].comodel_name, comodel)
        # M2M
        for fname, comodel in [
            ('lens_base_treatment_ordered_ids', 'optical.lens.treatment'),
            ('lens_extra_treatment_ordered_ids', 'optical.lens.treatment'),
            ('lens_tint_ordered_ids', 'optical.lens.tint'),
        ]:
            with self.subTest(field=fname):
                self.assertEqual(SOL._fields[fname].type, 'many2many')
                self.assertEqual(SOL._fields[fname].comodel_name, comodel)
        # Domains M2M treatments : base vs complement
        self.assertEqual(
            SOL._fields['lens_base_treatment_ordered_ids'].domain,
            [('treatment_type', '=', 'base')],
        )
        self.assertEqual(
            SOL._fields['lens_extra_treatment_ordered_ids'].domain,
            [('treatment_type', '=', 'complement')],
        )
        # Char
        self.assertEqual(SOL._fields['lens_other_note'].type, 'char')
        # Relations distinctes (garde-fou collision M2M)
        self.assertNotEqual(
            SOL._fields['lens_base_treatment_ordered_ids'].relation,
            SOL._fields['lens_extra_treatment_ordered_ids'].relation,
            "Les 2 M2M treatment doivent avoir des tables de jointure distinctes",
        )

    def test_lens_design_ordered_selection_mirrors_product_template(self):
        """AC-1.3 : lens_design_ordered miroir dynamique de product.template.lens_design (callable Selection)."""
        sol_selection = self.env['sale.order.line']._fields['lens_design_ordered']._description_selection(self.env)
        pt_selection = self.env['product.template']._fields['lens_design']._description_selection(self.env)
        self.assertEqual(sol_selection, pt_selection)

    def test_lens_material_ordered_selection_mirrors_product_template(self):
        """AC-1.3 : lens_material_ordered miroir dynamique de product.template.lens_material."""
        sol_selection = self.env['sale.order.line']._fields['lens_material_ordered']._description_selection(self.env)
        pt_selection = self.env['product.template']._fields['lens_material']._description_selection(self.env)
        self.assertEqual(sol_selection, pt_selection)

    # ------------------------------------------------------------------
    # Bloc B — Contrainte eye_side (AC-2) : 3 tests
    # ------------------------------------------------------------------

    def test_eye_side_required_on_lens_line_raises(self):
        """AC-2.1 : créer une ligne verre sans eye_side → ValidationError avec message exact."""
        with self.assertRaisesRegex(ValidationError, r"L'œil \(OD/OG\) est requis pour un verre"):
            self.env['sale.order'].create({
                'partner_id': self.patient.id,
                'order_line': [Command.create({
                    'product_id': self.product_lens.id,
                    'product_uom_qty': 1,
                    # eye_side manquant volontairement
                })],
            })

    def test_eye_side_not_required_on_non_lens_line(self):
        """AC-2.2 : ligne accessoire/frame/contact_lens sans eye_side → OK."""
        for product in (self.product_accessory, self.product_frame, self.product_contact):
            with self.subTest(optical_type=product.optical_type):
                order = self.env['sale.order'].create({
                    'partner_id': self.patient.id,
                    'order_line': [Command.create({
                        'product_id': product.id,
                        'product_uom_qty': 1,
                    })],
                })
                self.assertTrue(order.exists())

    def test_eye_side_constraint_skips_historical_lines_on_partial_write(self):
        """AC-2.3 : historique sans eye_side reste modifiable sur autres champs (fields-scoped constraint)."""
        order = self.env['sale.order'].create({'partner_id': self.patient.id})
        line = self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': self.product_lens.id,
            'product_uom_qty': 1,
            'eye_side': 'od',
        })
        # Simuler historique : vider eye_side via SQL brut (bypass Python constraint)
        self.env.cr.execute(
            "UPDATE sale_order_line SET eye_side = NULL WHERE id = %s",
            (line.id,),
        )
        line.invalidate_recordset(['eye_side'])
        self.assertFalse(line.eye_side)
        # Modifier UNIQUEMENT price_unit → OK (constrains ne fire pas)
        line.write({'price_unit': 42000.0})
        self.assertEqual(line.price_unit, 42000.0)
        # Modifier explicitement eye_side vers False + product_id (fires constraint) → doit lever
        with self.assertRaises(ValidationError):
            line.write({'eye_side': False, 'product_id': self.product_lens.id})

    # ------------------------------------------------------------------
    # Bloc C — Verrouillage post-confirmation (AC-3/4/6) : 5 tests
    # ------------------------------------------------------------------

    def test_seller_can_edit_snapshot_field_on_draft_so(self):
        """AC-3.1 : vendeur write sur ligne verre en draft → OK, aucun message posté."""
        order = self.env['sale.order'].with_user(self.user_vendeur).create({
            'partner_id': self.patient.id,
            'order_line': [Command.create({
                'product_id': self.product_lens.id,
                'product_uom_qty': 1,
                'eye_side': 'og',
                'lens_index_ordered_id': self.index_160.id,
            })],
        })
        msgs_before = len(order.message_ids)
        order.order_line.with_user(self.user_vendeur).write({'lens_index_ordered_id': self.index_167.id})
        self.assertEqual(order.order_line.lens_index_ordered_id, self.index_167)
        self.assertEqual(len(order.message_ids), msgs_before, "Aucun message diff attendu sur SO draft")

    def test_seller_cannot_edit_snapshot_field_after_confirmation(self):
        """AC-4.1 : vendeur write chaque snapshot post-confirmation → AccessError sur chacun des 10 champs."""
        cases = [
            ('eye_side', 'og'),
            ('lens_design_ordered', 'progressive'),
            ('lens_material_ordered', 'polycarbonate'),
            ('lens_index_ordered_id', self.index_167.id),
            ('lens_thickness_ordered_id', self.thickness_ultra.id),
            ('lens_brand_ordered_id', self.brand_essilor.id),
            ('lens_other_note', 'Note test S19-5'),
            ('lens_base_treatment_ordered_ids', [Command.set([self.treatment_photo.id])]),
            ('lens_extra_treatment_ordered_ids', [Command.set([self.treatment_ar.id])]),
            ('lens_tint_ordered_ids', [Command.set([self.tint_blanc.id])]),
        ]
        for field_name, value in cases:
            with self.subTest(field=field_name):
                # SO neuve à chaque itération (post-write partiel invalide le state pour le suivant)
                order, line = self._make_confirmed_lens_order()
                with self.assertRaisesRegex(AccessError, r"Ligne verre verrouillée après confirmation"):
                    line.with_user(self.user_vendeur).write({field_name: value})

    def test_seller_cannot_edit_product_id_after_confirmation_on_lens(self):
        """AC-4.1 : vendeur modifie product_id sur ligne verre confirmée → AccessError."""
        order, line = self._make_confirmed_lens_order()
        product_lens_bis = self.env['product.product'].create({
            'name': 'Verre Alt Test S19-5',
            'type': 'consu',
            'list_price': 25000.0,
            'taxes_id': [],
            'optical_type': 'lens',
        })
        with self.assertRaisesRegex(AccessError, r"Ligne verre verrouillée après confirmation"):
            line.with_user(self.user_vendeur).write({'product_id': product_lens_bis.id})

    def test_seller_can_edit_price_unit_after_confirmation_on_lens(self):
        """AC-4.3 : vendeur modifie price_unit (hors lock) sur ligne verre confirmée → OK."""
        order, line = self._make_confirmed_lens_order()
        line.with_user(self.user_vendeur).write({'price_unit': 45000.0})
        self.assertEqual(line.price_unit, 45000.0)

    def test_seller_can_edit_snapshot_field_after_confirmation_on_non_lens(self):
        """AC-6.1 : sur une ligne non-verre confirmée, notre lock ne s'applique pas.

        Note : `product_id` post-confirmation est bloqué par Odoo core (sale) sur
        TOUTES les lignes, indépendamment de notre lock — donc on ne peut pas
        tester le lock via product_id. On teste plutôt qu'un snapshot field
        (lens_other_note) peut être écrit sans déclencher notre AccessError
        « Ligne verre verrouillée après confirmation ».
        """
        order = self.env['sale.order'].with_user(self.user_vendeur).create({
            'partner_id': self.patient.id,
            'order_line': [Command.create({
                'product_id': self.product_accessory.id,
                'product_uom_qty': 1,
            })],
        })
        order.action_confirm()
        # Écrire un champ snapshot sur une ligne non-verre : notre lock est court-circuité
        order.order_line.with_user(self.user_vendeur).write({'lens_other_note': 'Note vendeur post-confirm'})
        self.assertEqual(order.order_line.lens_other_note, 'Note vendeur post-confirm')

    # ------------------------------------------------------------------
    # Bloc D — Autorisation manager + message diff (AC-5) : 3 tests
    # ------------------------------------------------------------------

    def test_manager_can_edit_lens_after_confirmation_and_posts_diff(self):
        """AC-5.1 : manager modifie lens_index_ordered_id post-confirmation → OK + message posté avec diff."""
        order, line = self._make_confirmed_lens_order()
        msgs_before = len(order.message_ids)
        line.with_user(self.user_responsable).write({'lens_index_ordered_id': self.index_167.id})
        self.assertEqual(line.lens_index_ordered_id, self.index_167)
        self.assertEqual(len(order.message_ids), msgs_before + 1, "1 message diff attendu")
        msg = order.message_ids[0]  # order desc → premier = plus récent
        self.assertIn('Modification post-confirmation ligne verre', msg.body)
        self.assertIn('lens_index_ordered_id', msg.body)
        self.assertIn('1.60 Test S19-5', msg.body)  # ancien
        self.assertIn('1.67 Test S19-5', msg.body)  # nouveau
        self.assertEqual(msg.subtype_id, self.env.ref('mail.mt_note'), "Doit être une note interne")

    def test_manager_write_same_value_posts_no_message(self):
        """AC-5.2 : manager écrit la même valeur → super().write() OK, aucun message posté."""
        order, line = self._make_confirmed_lens_order()
        msgs_before = len(order.message_ids)
        line.with_user(self.user_responsable).write({'lens_index_ordered_id': self.index_160.id})
        self.assertEqual(len(order.message_ids), msgs_before, "Aucun message attendu (diff = 0)")

    def test_manager_multi_field_write_posts_single_grouped_message(self):
        """AC-5.4 : manager modifie 2 champs en un seul write → 1 message avec 2 lignes de diff."""
        order, line = self._make_confirmed_lens_order()
        msgs_before = len(order.message_ids)
        line.with_user(self.user_responsable).write({
            'lens_index_ordered_id': self.index_167.id,
            'lens_thickness_ordered_id': self.thickness_ultra.id,
        })
        self.assertEqual(len(order.message_ids), msgs_before + 1, "1 seul message groupé attendu")
        msg = order.message_ids[0]
        self.assertIn('lens_index_ordered_id', msg.body)
        self.assertIn('lens_thickness_ordered_id', msg.body)

    def test_manager_can_edit_all_snapshot_fields_after_confirmation(self):
        """AC-5 (couverture exhaustive) : manager peut modifier CHACUN des 10 snapshot fields
        post-confirmation, chaque write pose un message diff sur order.message_ids.

        Ce test paramétré est la symétrie positive de test_seller_cannot_edit_snapshot_field_after_confirmation.
        Il exerce en particulier les 2 Selection callables (lens_design_ordered, lens_material_ordered)
        qui ne peuvent être formatées qu'en appelant field._description_selection(env) — les diff
        naïfs sur field.selection (callable brut) crashent.
        """
        cases = [
            ('eye_side', 'og'),
            ('lens_design_ordered', 'progressive'),
            ('lens_material_ordered', 'polycarbonate'),
            ('lens_index_ordered_id', self.index_167.id),
            ('lens_thickness_ordered_id', self.thickness_ultra.id),
            ('lens_brand_ordered_id', self.brand_essilor.id),
            ('lens_other_note', 'Note manager test S19-5'),
            ('lens_base_treatment_ordered_ids', [Command.set([self.treatment_photo.id])]),
            ('lens_extra_treatment_ordered_ids', [Command.set([self.treatment_ar.id])]),
            ('lens_tint_ordered_ids', [Command.set([self.tint_blanc.id])]),
        ]
        for field_name, value in cases:
            with self.subTest(field=field_name):
                order, line = self._make_confirmed_lens_order()
                msgs_before = len(order.message_ids)
                line.with_user(self.user_responsable).write({field_name: value})
                self.assertEqual(
                    len(order.message_ids), msgs_before + 1,
                    f"1 message diff attendu pour modification manager sur {field_name}",
                )
                msg = order.message_ids[0]
                self.assertIn('Modification post-confirmation ligne verre', msg.body)
                self.assertIn(field_name, msg.body)

    def test_vendor_access_error_includes_context(self):
        """M1 : l'AccessError vendeur doit identifier la ligne et le(s) champ(s) verrouillé(s)
        pour permettre à un support d'investiguer sans deviner."""
        order, line = self._make_confirmed_lens_order()
        with self.assertRaises(AccessError) as ctx:
            line.with_user(self.user_vendeur).write({'lens_index_ordered_id': self.index_167.id})
        msg = str(ctx.exception)
        self.assertIn('Ligne verre verrouillée après confirmation', msg)
        self.assertIn(self.product_lens.display_name, msg, "AccessError doit citer le produit")
        self.assertIn('lens_index_ordered_id', msg, "AccessError doit citer le(s) champ(s) modifié(s)")
