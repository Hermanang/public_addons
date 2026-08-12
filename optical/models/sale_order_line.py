# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


_LENS_SNAPSHOT_FIELDS = (
    'eye_side',
    'lens_design_ordered',
    'lens_material_ordered',
    'lens_index_ordered_id',
    'lens_base_treatment_ordered_ids',
    'lens_extra_treatment_ordered_ids',
    'lens_tint_ordered_ids',
    'lens_thickness_ordered_id',
    'lens_brand_ordered_id',
    'lens_other_note',
)
_LENS_LOCK_FIELDS = _LENS_SNAPSHOT_FIELDS + ('product_id',)


def _selection_lens_design(self):
    return self.env['product.template']._fields['lens_design'].selection


def _selection_lens_material(self):
    return self.env['product.template']._fields['lens_material'].selection


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # === Œil concerné (Story 19-5 AC-1.2) ===
    eye_side = fields.Selection(
        [('od', 'OD'), ('og', 'OG')],
        string="Œil",
        help=(
            "OD (œil droit) ou OG (œil gauche) — requis pour les lignes verres "
            "(product.optical_type='lens'). Contrôlé par contrainte Python : "
            "la ligne est refusée à la sauvegarde si ce champ est vide sur un verre."
        ),
    )

    # === Snapshot caractéristiques demandées (Story 19-5 AC-1.3) ===
    # Callables Selection = miroir dynamique du parent product.template.
    lens_design_ordered = fields.Selection(
        selection=_selection_lens_design,
        string="Design demandé",
        help=(
            "Design demandé par le client (miroir dynamique de product.template.lens_design). "
            "Indépendant du produit sélectionné : le vendeur peut demander « Progressif » "
            "et sélectionner un produit avec des propriétés différentes."
        ),
    )
    lens_material_ordered = fields.Selection(
        selection=_selection_lens_material,
        string="Matériau demandé",
        help=(
            "Matériau demandé par le client (miroir dynamique de product.template.lens_material). "
            "Indépendant du produit sélectionné."
        ),
    )
    lens_index_ordered_id = fields.Many2one(
        'optical.lens.index',
        string="Indice demandé",
        help="Indice de réfraction demandé par le client (référentiel Story 19-2).",
    )
    # Relation explicite obligatoire : les 2 M2M pointent vers le même comodel
    # (optical.lens.treatment) — sans relation= distinct, Odoo générerait la même
    # table de jointure pour les 2 champs → pollution silencieuse base/complément.
    lens_base_treatment_ordered_ids = fields.Many2many(
        'optical.lens.treatment',
        relation='sale_order_line_lens_base_treatment_rel',
        column1='order_line_id',
        column2='treatment_id',
        string="Traitements de base demandés",
        domain=[('treatment_type', '=', 'base')],
        help="Traitements de base demandés (photochromique, polarisé, blue-cut — Story 19-3).",
    )
    lens_extra_treatment_ordered_ids = fields.Many2many(
        'optical.lens.treatment',
        relation='sale_order_line_lens_extra_treatment_rel',
        column1='order_line_id',
        column2='treatment_id',
        string="Traitements complémentaires demandés",
        domain=[('treatment_type', '=', 'complement')],
        help="Traitements complémentaires demandés (antireflet, mirror, durcisseur — Story 19-3).",
    )
    lens_tint_ordered_ids = fields.Many2many(
        'optical.lens.tint',
        relation='sale_order_line_lens_tint_rel',
        column1='order_line_id',
        column2='tint_id',
        string="Teintes demandées",
        help="Teintes demandées par le client.",
    )
    lens_thickness_ordered_id = fields.Many2one(
        'optical.lens.thickness',
        string="Épaisseur demandée",
        help="Épaisseur demandée par le client (référentiel Story 19-1).",
    )
    lens_brand_ordered_id = fields.Many2one(
        'product.brand',
        string="Marque demandée",
        help="Marque demandée par le client (OCA product_brand).",
    )
    lens_other_note = fields.Char(
        string="Autre à préciser",
        help="Texte libre pour toute caractéristique non couverte par les champs structurés.",
    )

    # === Contrainte Python : eye_side requis pour un verre (AC-2) ===
    @api.constrains('eye_side', 'product_id')
    def _check_eye_side_required_for_lens(self):
        for line in self:
            if line.display_type:
                continue  # sections/notes n'ont pas de product_id
            if line.product_id.optical_type == 'lens' and not line.eye_side:
                raise ValidationError(_(
                    "L'œil (OD/OG) est requis pour un verre. Ligne : %s",
                    line.product_id.display_name,
                ))

    # === Override write() : verrouillage post-confirmation SO (AC-3/4/5/6) ===
    def write(self, vals):
        # 1. Court-circuit early-return si vals ne touche aucun champ verrouillé (AC-4.4 performance)
        touched = set(vals) & set(_LENS_LOCK_FIELDS)
        if not touched:
            return super().write(vals)

        # 2. Filtrer les lignes verres verrouillées (lens + SO state in sale/done)
        locked_lens_lines = self.filtered(
            lambda l: l.product_id.optical_type == 'lens'
            and l.order_id.state in ('sale', 'done')
        )
        if not locked_lens_lines:
            return super().write(vals)

        # 3. Check groupe : seul group_optical_manager peut modifier post-confirmation
        is_manager = self.env.user.has_group('optical.group_optical_manager')
        if not is_manager:
            first = locked_lens_lines[:1]
            raise AccessError(_(
                "Ligne verre verrouillée après confirmation. "
                "Contacter un responsable. "
                "(Ligne : %(product)s — Œil %(eye)s — Champ(s) modifié(s) : %(fields)s)",
                product=first.product_id.display_name or _("(sans produit)"),
                eye=self._format_eye_side_label(first.eye_side),
                fields=', '.join(sorted(touched)),
            ))

        # 4. Manager : capturer raw values (comparaison sémantique fiable)
        #    + formatted (message body lisible)
        old_raw = {
            line.id: {f: self._capture_raw_value(line, f) for f in touched}
            for line in locked_lens_lines
        }
        old_formatted = {
            line.id: {f: self._format_field_for_diff(line, f) for f in touched}
            for line in locked_lens_lines
        }

        # 5. Perform write
        result = super().write(vals)

        # 6. Post message chatter par ligne modifiée (uniquement si diff effectif)
        for line in locked_lens_lines:
            new_raw = {f: self._capture_raw_value(line, f) for f in touched}
            changed = [f for f in touched if old_raw[line.id][f] != new_raw[f]]
            if not changed:
                continue  # AC-5.2 : aucun changement effectif, pas de message
            new_formatted = {f: self._format_field_for_diff(line, f) for f in changed}
            changes_lines = [
                f"• {f} : {old_formatted[line.id][f]} → {new_formatted[f]}"
                for f in changed
            ]
            body = _(
                "Modification post-confirmation ligne verre par %(user)s :\n"
                "%(product)s — Œil %(eye)s\n%(changes)s",
                user=self.env.user.name,
                product=line.product_id.display_name,
                eye=self._format_eye_side_label(line.eye_side),
                changes='\n'.join(changes_lines),
            )
            line.order_id.message_post(
                body=body,
                subtype_xmlid='mail.mt_note',
            )

        return result

    def _format_eye_side_label(self, code):
        """Retourne le libellé lisible d'une valeur eye_side (Selection statique)."""
        if not code:
            return "N/A"
        return dict(self._fields['eye_side'].selection).get(code, code)

    def _capture_raw_value(self, line, field_name):
        """Capture la valeur brute d'un champ pour comparaison sémantique fiable.

        Utilisée pour détecter un vrai changement (identité des enregistrements),
        indépendamment du rendu display_name (qui peut ordonner ou coïncider
        entre homonymes). Le rendu lisible se fait ailleurs via _format_field_for_diff.
        """
        field = self._fields[field_name]
        value = line[field_name]
        if field.type == 'many2one':
            return value.id
        if field.type == 'many2many':
            return tuple(sorted(value.ids))
        return value  # selection, char, text, etc.

    def _format_field_for_diff(self, line, field_name):
        """Formatte lisiblement une valeur de champ pour le diff chatter."""
        field = self._fields[field_name]
        value = line[field_name]
        if field.type == 'many2one':
            return value.display_name if value else _("(vide)")
        if field.type == 'many2many':
            names = value.mapped('display_name')
            return ', '.join(names) if names else _("(aucun)")
        if field.type == 'selection':
            if not value:
                return _("(vide)")
            # field.selection peut être une callable (miroir dynamique) → utiliser
            # _description_selection qui résout la callable dans le contexte env.
            selection = dict(field._description_selection(self.env))
            return selection.get(value, value)
        # Char / Text : tronquer si long pour éviter des messages chatter géants
        if not value:
            return _("(vide)")
        text = str(value)
        return text if len(text) <= 100 else text[:100] + '…'

    # ==================================================================
    # Proxies contrôles footer order_line vers sale.order (Story 19-7 refactor)
    # ==================================================================
    # Pattern natif Odoo (cf. sale.order.line.action_add_from_catalog) : les
    # boutons dans `<control>` d'une <list> sont appelés sur le CHILD (SOL),
    # avec `order_id` propagé en contexte. On délègue à sale.order.

    def _browse_order_from_control_ctx(self):
        order_id = self.env.context.get('order_id')
        if not order_id:
            raise ValidationError(_(
                "Contrôle catalogue verre appelé sans order_id — ce bouton "
                "doit être invoqué depuis les lignes d'une commande."
            ))
        order = self.env['sale.order'].browse(order_id)
        # check_access délègue aux ACL/record-rules standard sale.order —
        # évite qu'un contexte forgé pointe vers une SO sur laquelle
        # l'utilisateur n'a pas de droit d'écriture.
        order.check_access('write')
        return order

    def action_add_lens_od(self):
        return self._browse_order_from_control_ctx().action_add_lens_od()

    def action_add_lens_og(self):
        return self._browse_order_from_control_ctx().action_add_lens_og()
