# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # === Classification optique ===
    optical_type = fields.Selection([
        ('frame', 'Monture'),
        ('lens', 'Verre'),
        ('contact_lens', 'Lentille de contact'),
        ('accessory', 'Accessoire'),
        ('service', 'Service'),
    ], string="Type optique", index=True)

    # === Attributs monture (visible si optical_type == 'frame') ===
    frame_shape = fields.Selection([
        ('rectangular', 'Rectangulaire'),
        ('oval', 'Ovale'),
        ('square', 'Carré'),
        ('browline', 'Browline'),
        ('aviator', 'Aviateur'),
        ('round', 'Rond'),
        ('butterfly', 'Papillon'),
        ('geometric', 'Géométrique'),
        ('heart', 'Cœur'),
    ], string="Forme")
    frame_gender = fields.Selection([
        ('man', 'Homme'),
        ('woman', 'Femme'),
        ('mixed', 'Mixte'),
        ('boy', 'Garçon'),
        ('girl', 'Fille'),
    ], string="Genre")
    frame_rim_type = fields.Selection([
        ('full_rim', 'Cerclée'),
        ('semi_rimless', 'Semi-cerclée'),
        ('rimless', 'Non cerclée'),
    ], string="Type de cerclage")
    lens_width = fields.Integer(string="Largeur verres (mm)")
    bridge_width = fields.Integer(string="Largeur pont (mm)")
    temple_length = fields.Integer(string="Longueur branches (mm)")
    # product_brand_id : fourni par OCA product_brand — NE PAS RECREER
    frame_material_ids = fields.Many2many(
        'optical.frame.material', string="Matériaux")
    frame_color_ids = fields.Many2many(
        'optical.frame.color', string="Couleurs")
    frame_usage_ids = fields.Many2many(
        'optical.frame.usage', string="Usages")

    # === Attributs verre (visible si optical_type in ('lens', 'contact_lens')) ===
    lens_design = fields.Selection([
        ('single_vision', 'Unifocal'),
        ('progressive', 'Progressif'),
        ('bifocal', 'Bifocal'),
        ('degressive', 'Dégressif'),
        ('mid_distance', 'Mi-distance'),
    ], string="Design")
    lens_surface = fields.Selection([
        ('spherical', 'Sphérique'),
        ('aspherical', 'Asphérique'),
        ('double_aspherical', 'Double asphérique'),
        ('freeform', 'Freeform'),
    ], string="Surface")
    lens_material = fields.Selection([
        ('organic', 'Organique'),
        ('polycarbonate', 'Polycarbonate'),
        ('mineral', 'Minérale'),
        ('trivex', 'Trivex'),
    ], string="Matériau")
    lens_index_id = fields.Many2one(
        'optical.lens.index',
        string="Indice de réfraction",
        help="Indice de réfraction du verre — sélectionner dans le référentiel Configuration → Attributs → Indices verres",
    )
    lens_diameter = fields.Float(string="Diamètre (mm)")
    lens_thickness_id = fields.Many2one(
        'optical.lens.thickness',
        string="Épaisseur",
        help=(
            "Épaisseur du verre — sélectionner dans le référentiel "
            "Configuration → Attributs → Épaisseurs verres.\n\n"
            "Utilisé pour filtrer les candidats dans le wizard vente "
            "et refléter la caractéristique demandée sur la ligne "
            "de vente (Stories 19-5/6/7)."
        ),
    )
    lens_treatment_ids = fields.Many2many(
        'optical.lens.treatment', string="Traitements")
    lens_tint_ids = fields.Many2many(
        'optical.lens.tint', string="Teintes")

    # ==================================================================
    # Formateurs verre correcteur — nom Format A + description Format 2
    # (S19-9, révisé 2026-07-27). Utilisés par le wizard
    # `optical.lens.wizard` pour :
    #   - Pré-remplir `default_name` / `default_description_sale` du form
    #     product.template quand on crée un nouveau verre via l'empty state
    #     de l'assistant.
    #   - Renseigner `sale.order.line.name` (description ligne de commande /
    #     PDF devis-facture) à la création d'une SOL verre via le wizard.
    # ==================================================================

    # Libellés clients pour OD/OG (le Selection eye_side côté SOL n'a que
    # 'OD'/'OG' — on préfère un libellé complet dans la description PDF).
    _LENS_EYE_LABELS = {'od': "Œil droit", 'og': "Œil gauche"}

    def _get_lens_default_name(self):
        """Nom Format A calculé à partir des champs verre du template.

        Format : ``Verre [Traitements] [Design] [Teintes]`` — colle à la
        convention observée dans le catalogue existant (~90% des 970 verres
        sont nommés ``Verre Antireflet Unifocal Photogray``, etc.).
        """
        self.ensure_one()
        base_tx = self.lens_treatment_ids.filtered(lambda t: t.treatment_type == 'base')
        extra_tx = self.lens_treatment_ids.filtered(lambda t: t.treatment_type == 'complement')
        return self._format_lens_default_name(
            design=self.lens_design, material=self.lens_material,
            base_treatments=base_tx, extra_treatments=extra_tx,
            tints=self.lens_tint_ids,
        )

    def _get_lens_default_description(self, eye_side=None):
        """Description Format 2 (compact 3 lignes) basée sur le NOM RÉEL
        du produit + attributs — cf. `_format_lens_default_description`.

        Header : ``[REF] Nom`` si `default_code` renseigné, sinon ``Nom``.
        On respecte le libellé volontairement choisi par le vendeur au lieu
        de régénérer un nom synthétique Format A (bug S19-9e).
        """
        self.ensure_one()
        header_name = (
            "[%s] %s" % (self.default_code, self.name)
            if self.default_code else self.name
        )
        base_tx = self.lens_treatment_ids.filtered(lambda t: t.treatment_type == 'base')
        extra_tx = self.lens_treatment_ids.filtered(lambda t: t.treatment_type == 'complement')
        return self._format_lens_default_description(
            product_name=header_name,
            design=self.lens_design, material=self.lens_material,
            index=self.lens_index_id, thickness=self.lens_thickness_id,
            brand=self.product_brand_id,
            base_treatments=base_tx, extra_treatments=extra_tx,
            tints=self.lens_tint_ids, eye_side=eye_side,
        )

    @api.model
    def _format_lens_default_name(self, design=None, material=None,
                                  base_treatments=None, extra_treatments=None,
                                  tints=None):
        """Format A — ``Verre [Traitements de base] [Traitements compl.] [Design] [Teintes]``.

        Cadré sur la convention réelle du catalogue (top 800/970 : ``Verre
        Antireflet Unifocal Photogray``). Le matériau et l'épaisseur ne
        figurent PAS dans le nom (attributs séparés dans le form produit).
        Fallback : ``Verre`` seul si aucun critère fourni.
        """
        parts = [_("Verre")]
        for tx in (base_treatments or []):
            parts.append(tx.name)
        for tx in (extra_treatments or []):
            parts.append(tx.name)
        if design:
            parts.append(self._get_lens_selection_label('lens_design', design))
        for tint in (tints or []):
            parts.append(tint.name)
        return ' '.join(p for p in parts if p)

    @api.model
    def _format_lens_default_description(self, product_name=None,
                                         design=None, material=None,
                                         index=None, thickness=None, brand=None,
                                         base_treatments=None, extra_treatments=None,
                                         tints=None, eye_side=None):
        """Format 2 — compact 3 lignes (validé 2026-07-27), prêt PDF.

        Structure (chaque token de la ligne 2 et la ligne 3 elle-même sont
        optionnels — skippés si les champs correspondants sont vides) :

            <product_name ou Format A> [— Œil <droit|gauche>]
            <Design> · <Matériau [Indice]> · <Épaisseur> · <Marque>
            Traitements : <A + B + C> · Teinte : <X>

        Header : si ``product_name`` est fourni, il est utilisé tel quel
        (idéal pour un produit existant avec un nom volontairement choisi,
        ex: ``[V-1234] Verre`` — bug S19-9e). Sinon fallback sur le nom
        auto Format A depuis les critères (utile pour préparer la
        description d'un nouveau produit pas encore nommé).

        Choix vs Format 1 (bullets) : plus dense verticalement, plus
        élégant sur devis compact — retenu par le client après essai
        visuel du bulleted layout.
        """
        if product_name:
            header = product_name
        else:
            header = self._format_lens_default_name(
                design=design, material=material,
                base_treatments=base_treatments, extra_treatments=extra_treatments,
                tints=tints,
            )
        if eye_side:
            eye_label = self._LENS_EYE_LABELS.get(eye_side, eye_side.upper())
            header = _("%(name)s — %(eye)s", name=header, eye=eye_label)
        lines = [header]

        # Ligne 2 : Design · Matériau [Indice] · Épaisseur · Marque
        line2_parts = []
        if design:
            line2_parts.append(self._get_lens_selection_label('lens_design', design))
        if material or index:
            material_str = self._get_lens_selection_label('lens_material', material) if material else ''
            if material_str and index:
                line2_parts.append(_("%(mat)s %(idx)s", mat=material_str, idx=index.value))
            elif material_str:
                line2_parts.append(material_str)
            elif index:
                line2_parts.append(_("Indice %s") % index.value)
        if thickness:
            line2_parts.append(thickness.name)
        if brand:
            line2_parts.append(brand.name)
        if line2_parts:
            lines.append(' · '.join(line2_parts))

        # Ligne 3 : Traitements : A + B · Teinte : X
        line3_parts = []
        all_treatments = list(base_treatments or []) + list(extra_treatments or [])
        if all_treatments:
            line3_parts.append(_("Traitements : %s") % ' + '.join(t.name for t in all_treatments))
        if tints:
            line3_parts.append(_("Teinte : %s") % ' + '.join(t.name for t in tints))
        if line3_parts:
            lines.append(' · '.join(line3_parts))

        return '\n'.join(lines)

    @api.model
    def _get_lens_selection_label(self, field_name, key):
        """Résout un code Selection (lens_design / lens_material / lens_surface)
        vers son libellé humain via `_description_selection` — supporte la
        forme callable Odoo 18."""
        if not key:
            return ''
        selection = dict(self._fields[field_name]._description_selection(self.env))
        return selection.get(key, key)

    # ==================================================================
    # Auto-ajout à la commande après création via l'empty state du wizard
    # (S19-9c)
    #
    # Bug : le form product.template ouvert par `action_open_new_product`
    # est en `target='new'` → il remplace le wizard verre dans la pile de
    # modales. Au save, sans hook, le nouveau verre était bien créé mais
    # jamais rattaché à la ligne de commande — le vendeur devait le
    # rechercher manuellement.
    #
    # Fix : on récupère `order_id` + `eye_side` en contexte (posés par
    # `wizard.action_open_new_product`) et on délègue au flow standard
    # `sale.order._update_order_line_info` qui gère snapshot S19-5 +
    # eye_side. Ne se déclenche qu'au CREATE (pas au write suivant), donc
    # une seule SOL par nouveau produit. Silencieusement no-op si le
    # contexte n'est pas posé (comportement natif préservé ailleurs).
    # ==================================================================
    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        ctx = self.env.context
        order_id = ctx.get('optical_new_lens_order_id')
        eye_side = ctx.get('optical_new_lens_eye_side')
        if not (order_id and eye_side):
            return products
        SO = self.env['sale.order'].browse(order_id).exists()
        if not SO or SO.state == 'cancel':
            return products
        for product in products.filtered(lambda p: p.optical_type == 'lens' and p.sale_ok):
            variant = product.product_variant_ids[:1]
            if not variant:
                continue
            try:
                SO.optical_catalog_pending_eye_side = eye_side
                SO._update_order_line_info(variant.id, 1)
            except Exception:
                _logger.exception(
                    "S19-9c : échec auto-ajout du nouveau verre %s à la SO %s "
                    "(œil %s) — le produit est créé mais la ligne devra être "
                    "ajoutée manuellement.",
                    product.id, SO.id, eye_side,
                )
        return products
