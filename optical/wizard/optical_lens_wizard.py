# -*- coding: utf-8 -*-
"""Wizard TransientModel de sélection verre correcteur.

Implémentation retenue (S19-9) pour l'ajout de verres correcteurs sur une
commande. Form view target='new' avec sidebar filtres à gauche et kanban
embarqué de candidats à droite, labels au-dessus des inputs, bandeau
filtres actifs, empty state avec CTA « Créer un nouveau verre ».

Flow métier : `sale.order._action_add_lens_side(side)` ouvre le wizard →
critères repris auto de la paire (P1 métier) → clic « Ajouter » sur une
card → `sale.order._update_order_line_info` crée la SOL avec eye_side +
snapshot 10 champs (S19-5).
"""

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


def _sel_lens_design(self):
    """Miroir dynamique Selection depuis product.template.lens_design."""
    return self.env['product.template']._fields['lens_design'].selection


def _sel_lens_material(self):
    return self.env['product.template']._fields['lens_material'].selection


def _sel_lens_surface(self):
    return self.env['product.template']._fields['lens_surface'].selection


class OpticalLensWizard(models.TransientModel):
    _name = 'optical.lens.wizard'
    _description = "Sélection verre correcteur"

    # Champs de critères recopiés d'un wizard OD → OG (et inversement) pour
    # que le vendeur ne re-saisisse pas les caractéristiques : en optique, la
    # paire a par défaut les mêmes specs, seule la prescription varie.
    _CARRYOVER_FIELDS = (
        'lens_design', 'lens_material', 'lens_surface',
        'lens_index_id', 'lens_thickness_id', 'product_brand_id',
        'lens_tint_ids', 'base_treatment_ids', 'extra_treatment_ids',
    )

    # === Contexte ===
    order_id = fields.Many2one(
        'sale.order', string="Commande", required=True, ondelete='cascade',
    )
    eye_side = fields.Selection(
        [('od', 'OD (Œil droit)'), ('og', 'OG (Œil gauche)')],
        string="Œil", required=True,
        help="OD / OG — recopié sur la ligne de vente créée (contrainte S19-5).",
    )
    partner_display = fields.Char(
        related='order_id.partner_id.name', string="Client", readonly=True,
    )

    # === Critères filtres (les 9 caractéristiques du fichier VERRES.xlsx) ===
    lens_design = fields.Selection(
        selection=_sel_lens_design, string="Design",
    )
    lens_material = fields.Selection(
        selection=_sel_lens_material, string="Matériau",
    )
    lens_surface = fields.Selection(
        selection=_sel_lens_surface, string="Surface",
    )
    lens_index_id = fields.Many2one(
        'optical.lens.index', string="Indice",
    )
    lens_thickness_id = fields.Many2one(
        'optical.lens.thickness', string="Épaisseur",
    )
    product_brand_id = fields.Many2one(
        'product.brand', string="Marque",
    )
    lens_tint_ids = fields.Many2many(
        'optical.lens.tint',
        relation='optical_lens_wizard_tint_rel',
        column1='wizard_id', column2='tint_id',
        string="Teintes",
    )
    base_treatment_ids = fields.Many2many(
        'optical.lens.treatment',
        relation='optical_lens_wizard_base_treat_rel',
        column1='wizard_id', column2='treatment_id',
        string="Traitement de base",
        domain=[('treatment_type', '=', 'base')],
    )
    extra_treatment_ids = fields.Many2many(
        'optical.lens.treatment',
        relation='optical_lens_wizard_extra_treat_rel',
        column1='wizard_id', column2='treatment_id',
        string="Traitement complémentaire",
        domain=[('treatment_type', '=', 'complement')],
    )
    search_text = fields.Char(string="Recherche libre")

    # === Résultat compute — verres candidats ===
    candidate_ids = fields.Many2many(
        'product.product',
        relation='optical_lens_wizard_candidate_rel',
        column1='wizard_id', column2='product_id',
        string="Verres candidats",
        compute='_compute_candidate_ids',
        store=False,
    )
    candidate_count = fields.Integer(
        string="Nombre de candidats",
        compute='_compute_candidate_ids',
    )
    active_filter_summary = fields.Char(
        string="Filtres actifs",
        compute='_compute_active_filter_summary',
        help="Résumé texte des critères sélectionnés — pilote l'affichage "
             "du bandeau récap et l'activation des boutons Effacer/Reset.",
    )
    # Récap des verres déjà présents sur la commande (S19-9f) — le vendeur
    # les voit sans devoir fermer le wizard pour aller regarder la SO.
    existing_lens_lines_count = fields.Integer(
        string="Nombre de verres sur la commande",
        compute='_compute_existing_lens_lines_summary',
    )
    existing_lens_lines_summary = fields.Char(
        string="Verres déjà sur la commande",
        compute='_compute_existing_lens_lines_summary',
    )

    @api.depends(
        'order_id.order_line.product_id',
        'order_id.order_line.eye_side',
        'order_id.order_line.product_uom_qty',
    )
    def _compute_existing_lens_lines_summary(self):
        for wiz in self:
            lens_lines = wiz.order_id.order_line.filtered(
                lambda l: l.product_id
                and l.product_id.product_tmpl_id.optical_type == 'lens'
                and l.eye_side
            )
            wiz.existing_lens_lines_count = len(lens_lines)
            if not lens_lines:
                wiz.existing_lens_lines_summary = ''
                continue
            by_eye = {'od': [], 'og': []}
            for line in lens_lines:
                if line.eye_side in by_eye:
                    by_eye[line.eye_side].append(line)
            parts = []
            for eye_key, eye_label in (('od', "OD"), ('og', "OG")):
                if by_eye[eye_key]:
                    items = []
                    for line in by_eye[eye_key]:
                        name = line.product_id.name or ''
                        if len(name) > 32:
                            name = name[:29] + '…'
                        qty = int(line.product_uom_qty)
                        items.append("%s (×%d)" % (name, qty) if qty > 1 else name)
                    parts.append("%s : %s" % (eye_label, ', '.join(items)))
            wiz.existing_lens_lines_summary = ' · '.join(parts)

    @api.depends(
        'lens_design', 'lens_material', 'lens_surface',
        'lens_index_id', 'lens_thickness_id', 'product_brand_id',
        'lens_tint_ids', 'base_treatment_ids', 'extra_treatment_ids',
    )
    def _compute_active_filter_summary(self):
        for wiz in self:
            parts = []
            # Selections : résoudre le libellé humain (fr) via _description_selection
            for fname in ('lens_design', 'lens_material', 'lens_surface'):
                val = wiz[fname]
                if val:
                    sel = dict(wiz._fields[fname]._description_selection(wiz.env))
                    parts.append(sel.get(val, val))
            # M2O : display_name
            for fname in ('lens_index_id', 'lens_thickness_id', 'product_brand_id'):
                rec = wiz[fname]
                if rec:
                    parts.append(rec.display_name)
            # M2M : chaque display_name
            for fname in ('lens_tint_ids', 'base_treatment_ids', 'extra_treatment_ids'):
                for rec in wiz[fname]:
                    parts.append(rec.display_name)
            wiz.active_filter_summary = ' · '.join(parts)

    @api.depends(
        'lens_design', 'lens_material', 'lens_surface',
        'lens_index_id', 'lens_thickness_id', 'product_brand_id',
        'lens_tint_ids', 'base_treatment_ids', 'extra_treatment_ids',
        'search_text',
    )
    def _compute_candidate_ids(self):
        for wiz in self:
            domain = [
                ('product_tmpl_id.optical_type', '=', 'lens'),
                ('sale_ok', '=', True),
            ]
            if wiz.lens_design:
                domain.append(('product_tmpl_id.lens_design', '=', wiz.lens_design))
            if wiz.lens_material:
                domain.append(('product_tmpl_id.lens_material', '=', wiz.lens_material))
            if wiz.lens_surface:
                domain.append(('product_tmpl_id.lens_surface', '=', wiz.lens_surface))
            if wiz.lens_index_id:
                domain.append(('product_tmpl_id.lens_index_id', '=', wiz.lens_index_id.id))
            if wiz.lens_thickness_id:
                domain.append(('product_tmpl_id.lens_thickness_id', '=', wiz.lens_thickness_id.id))
            if wiz.product_brand_id:
                domain.append(('product_tmpl_id.product_brand_id', '=', wiz.product_brand_id.id))
            for tint in wiz.lens_tint_ids:
                domain.append(('product_tmpl_id.lens_tint_ids', '=', tint.id))
            for tr in wiz.base_treatment_ids:
                domain.append(('product_tmpl_id.lens_treatment_ids', '=', tr.id))
            for tr in wiz.extra_treatment_ids:
                domain.append(('product_tmpl_id.lens_treatment_ids', '=', tr.id))
            q = (wiz.search_text or '').strip()
            if q:
                domain += [
                    '|', '|',
                    ('name', 'ilike', q),
                    ('default_code', 'ilike', q),
                    ('barcode', 'ilike', q),
                ]
            products = self.env['product.product'].search(domain, limit=200)
            wiz.candidate_ids = products
            wiz.candidate_count = len(products)

    # === Reprise critères OD → OG (S19-9 P1) ===
    #
    # Métier optique : en montage d'une paire de verres, les caractéristiques
    # (design, matériau, indice, teintes, traitements, épaisseur, marque) sont
    # identiques sur les 2 yeux dans l'immense majorité des cas — seule la
    # prescription varie. Reset des filtres entre OD et OG = re-saisie inutile.
    def _get_carryover_criteria(self):
        """Retourne un dict {field: value} des critères actuels à recopier
        sur un nouveau wizard (autre œil). Les M2M utilisent Command.set."""
        self.ensure_one()
        vals = {}
        for fname in self._CARRYOVER_FIELDS:
            field = self._fields[fname]
            val = self[fname]
            if field.type == 'many2many':
                if val:
                    vals[fname] = [Command.set(val.ids)]
            elif field.type == 'many2one':
                if val:
                    vals[fname] = val.id
            else:  # selection
                if val:
                    vals[fname] = val
        return vals

    @api.model
    def default_get(self, fields_list):
        """Pré-remplit les critères depuis le dernier wizard de la même SO.

        Déclenché quand `sale.order._action_add_lens_side` pose
        ``default_carryover_from_wizard_id`` en context (l'ID du wizard OD
        précédent quand on ouvre OG, par exemple). Sans contexte, comportement
        Odoo standard (tous les champs vides).
        """
        vals = super().default_get(fields_list)
        prev_id = self.env.context.get('default_carryover_from_wizard_id')
        if prev_id:
            prev = self.browse(prev_id).exists()
            if prev:
                vals.update(prev._get_carryover_criteria())
        return vals

    def action_reset_filters(self):
        """Réinitialise tous les critères de recherche (bouton bandeau + empty state)."""
        self.ensure_one()
        self.write({
            'lens_design': False,
            'lens_material': False,
            'lens_surface': False,
            'lens_index_id': False,
            'lens_thickness_id': False,
            'product_brand_id': False,
            'lens_tint_ids': [Command.clear()],
            'base_treatment_ids': [Command.clear()],
            'extra_treatment_ids': [Command.clear()],
            'search_text': False,
        })
        # Ré-ouvrir le wizard pour rafraîchir la vue (candidate_ids recompute)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'optical.lens.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_new_product(self):
        """CTA de l'état vide : ouvre le form de création d'un nouveau verre
        (product.template) pré-rempli avec les critères du wizard.

        Le vendeur crée le verre manquant sans quitter le contexte de la
        commande, puis revient au wizard pour l'ajouter (double clic sur
        « + Verre OD/OG » côté SO).
        """
        self.ensure_one()
        Product = self.env['product.template']
        # Nom Format A + description Format 1 générés depuis les critères en cours
        # (les traitements sont recomposés côté template en un seul M2M car
        # `product.template.lens_treatment_ids` n'est pas splitté base/complément).
        default_name = Product._format_lens_default_name(
            design=self.lens_design, material=self.lens_material,
            base_treatments=self.base_treatment_ids,
            extra_treatments=self.extra_treatment_ids,
            tints=self.lens_tint_ids,
        )
        default_description = Product._format_lens_default_description(
            # Passe le nom Format A qu'on vient de générer comme header —
            # le nouveau produit n'a pas encore de nom volontaire ni de
            # default_code, donc on utilise le nom synthétique proposé.
            product_name=default_name,
            design=self.lens_design, material=self.lens_material,
            index=self.lens_index_id, thickness=self.lens_thickness_id,
            brand=self.product_brand_id,
            base_treatments=self.base_treatment_ids,
            extra_treatments=self.extra_treatment_ids,
            tints=self.lens_tint_ids,
        )
        defaults = {
            'default_optical_type': 'lens',
            'default_sale_ok': True,
            'default_name': default_name,
            'default_description_sale': default_description,
            # Auto-rattachement à la commande au save du nouveau produit
            # (S19-9c) — consommé par `product.template.create()`. Sans ça,
            # le nouveau verre est créé mais jamais ajouté à la ligne de
            # devis (target='new' remplace le wizard dans la pile de modales
            # → aucun retour possible côté client).
            'optical_new_lens_order_id': self.order_id.id,
            'optical_new_lens_eye_side': self.eye_side,
        }
        if self.lens_design:
            defaults['default_lens_design'] = self.lens_design
        if self.lens_material:
            defaults['default_lens_material'] = self.lens_material
        if self.lens_surface:
            defaults['default_lens_surface'] = self.lens_surface
        if self.lens_index_id:
            defaults['default_lens_index_id'] = self.lens_index_id.id
        if self.lens_thickness_id:
            defaults['default_lens_thickness_id'] = self.lens_thickness_id.id
        if self.product_brand_id:
            defaults['default_product_brand_id'] = self.product_brand_id.id
        if self.lens_tint_ids:
            defaults['default_lens_tint_ids'] = [Command.set(self.lens_tint_ids.ids)]
        # Les 2 M2M de traitements pointent sur le même M2M produit ; on fusionne
        treatments = self.base_treatment_ids | self.extra_treatment_ids
        if treatments:
            defaults['default_lens_treatment_ids'] = [Command.set(treatments.ids)]
        return {
            'type': 'ir.actions.act_window',
            'name': _("Nouveau verre"),
            'res_model': 'product.template',
            'view_mode': 'form',
            'target': 'new',
            'context': defaults,
        }

    # === Action : ajouter un verre à la commande ===
    def action_add_line(self, product_id):
        """Appelée par le bouton "Ajouter" sur chaque ligne candidat.

        Persiste `optical_catalog_pending_eye_side` sur la SO (comme le fait
        `action_add_lens_od`) puis délègue à `_update_order_line_info` qui gère
        le snapshot S19-5 + eye_side. Le wizard reste ouvert pour ajout multiple
        (le vendeur peut ajouter plusieurs verres OD sans quitter la modale).

        Retour (S19-9f) : `display_notification` + `next` = act_window de
        réouverture. Le toast donne un feedback instantané au vendeur (la
        modale masque la SO derrière) ; le `next` réouvre le wizard qui
        recompute alors `existing_lens_lines_summary` avec la nouvelle SOL.
        """
        self.ensure_one()
        if not product_id:
            raise UserError(_("Aucun verre sélectionné."))
        if not self.order_id or not self.eye_side:
            raise UserError(_("Contexte œil ou commande invalide."))
        product = self.env['product.product'].browse(product_id)
        if not product.exists():
            raise UserError(_("Verre introuvable ou supprimé."))
        # Assure que _update_order_line_info trouve bien l'œil
        self.order_id.optical_catalog_pending_eye_side = self.eye_side
        existing = self.order_id.order_line.filtered(
            lambda l: l.product_id.id == product_id and l.eye_side == self.eye_side
        )
        new_qty = (existing.product_uom_qty if existing else 0) + 1
        self.order_id._update_order_line_info(product_id, new_qty)
        # Rafraîchir le wizard : la SOL vient d'être créée
        self.order_id.invalidate_recordset()

        eye_label = self.env['product.template']._LENS_EYE_LABELS.get(
            self.eye_side, self.eye_side.upper(),
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Verre ajouté"),
                'message': _(
                    "« %(product)s » ajouté à la commande (%(eye)s).",
                    product=product.name, eye=eye_label,
                ),
                'type': 'success',
                'sticky': False,
                # Réouvre le wizard après le toast — recompute
                # existing_lens_lines_summary → le bandeau récap se met à jour.
                # `views` est REQUIS ici (client `doAction` sur next appelle
                # `.map()` dessus) — contrairement au retour direct d'un
                # bouton où `view_mode` seul est normalisé.
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'optical.lens.wizard',
                    'res_id': self.id,
                    'views': [[False, 'form']],
                    'view_mode': 'form',
                    'target': 'new',
                },
            },
        }

    def action_close(self):
        """Ferme le wizard, retour à la SO."""
        return {'type': 'ir.actions.act_window_close'}
