# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProductProduct(models.Model):
    _inherit = 'product.product'

    # === Badge stock optique (compute non stocké — cadrage Q13) ===
    optical_stock_badge_type = fields.Selection(
        [
            ('in_stock', 'En stock'),
            ('mto', 'À commander'),
            ('stockout', 'Rupture'),
        ],
        string="État stock optique",
        compute='_compute_optical_stock_badge',
        store=False,
        help=(
            "État de disponibilité stock affiché dans le catalogue verre. "
            "Trois états : 'in_stock' (qty > 0), 'mto' (0 stock + route MTO), "
            "'stockout' (0 stock sans route). Cadrage Q13 — jamais bloquant."
        ),
    )
    optical_stock_badge_display = fields.Char(
        string="Dispo stock",
        compute='_compute_optical_stock_badge',
        store=False,
        help="Libellé badge stock formaté pour affichage (widget='badge').",
    )

    @api.depends(
        'product_tmpl_id.optical_type',
        'qty_available',
        'product_tmpl_id.route_ids',
        'categ_id.route_ids',
    )
    def _compute_optical_stock_badge(self):
        """Calcule le badge stock 3 états pour les produits `optical_type='lens'`.

        Non-lens → badge=False (cadrage Q13 restreint aux verres correcteurs).
        MTO détectée via `stock.route_warehouse0_mto` (route produit OU catégorie —
        cf. D-1 : purchase_stock non déclaré en dépendance, Buy route ignorée).

        Note : les routes sont lues depuis `product_tmpl_id.route_ids` (le field
        `route_ids` est défini sur `product.template` par le module `stock`).
        """
        mto_route = self.env.ref('stock.route_warehouse0_mto', raise_if_not_found=False)
        for product in self:
            if product.product_tmpl_id.optical_type != 'lens':
                product.optical_stock_badge_type = False
                product.optical_stock_badge_display = False
                continue

            qty = product.qty_available
            if qty > 0:
                product.optical_stock_badge_type = 'in_stock'
                product.optical_stock_badge_display = _("● En stock (%d)") % int(qty)
                continue

            has_mto = False
            if mto_route:
                template_routes = product.product_tmpl_id.route_ids
                categ_routes = product.categ_id.route_ids
                has_mto = mto_route in template_routes or mto_route in categ_routes
            if has_mto:
                product.optical_stock_badge_type = 'mto'
                product.optical_stock_badge_display = _("○ À commander")
            else:
                product.optical_stock_badge_type = 'stockout'
                product.optical_stock_badge_display = _("⚠ Rupture")

    def action_add_to_optical_wizard(self):
        """Helper appelé par le bouton "Ajouter" dans le kanban embarqué du
        wizard `optical.lens.wizard`. Lit `optical_wizard_id` du contexte
        (propagé par `<field context=...>` de la form view) et délègue à
        `wizard.action_add_line(self.id)` qui gère snapshot S19-5 + eye_side.
        """
        self.ensure_one()
        wizard_id = self.env.context.get('optical_wizard_id')
        if not wizard_id:
            raise UserError(_(
                "Contexte wizard manquant. Ce bouton doit être appelé depuis "
                "l'assistant sélection verre."
            ))
        wizard = self.env['optical.lens.wizard'].browse(wizard_id)
        if not wizard.exists():
            raise UserError(_(
                "L'assistant sélection verre est expiré. Merci de rouvrir depuis la commande."
            ))
        return wizard.action_add_line(self.id)
