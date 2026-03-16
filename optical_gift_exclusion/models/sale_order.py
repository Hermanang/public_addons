# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_create_split_invoices(self):
        """Propager is_gift (SO line) → is_gift (invoice line) sur les factures (chemin sans PEC)."""
        self.ensure_one()

        # Si PEC approuvee, super() delegue a pec.action_create_invoices()
        # dont l'override gere deja is_gift — rien a faire ici.
        if self.pec_id and self.pec_id.state == 'approved':
            return super().action_create_split_invoices()

        # Chemin direct (sans PEC) : collecter les flags gift
        product_lines = self.order_line.filtered(
            lambda l: not l.display_type and l.product_uom_qty > 0,
        )
        gift_flags = [line.is_gift for line in product_lines]

        # Factures existantes avant creation
        existing_ids = self.env['account.move'].sudo().search([
            ('insurance_sale_order_id', '=', self.id),
        ]).ids

        result = super().action_create_split_invoices()

        # Marquer is_gift sur les nouvelles factures
        # sudo() : les droits utilisateur ont deja ete verifies en amont
        # Matching positionnel (zip) : suppose que les lignes facture sont
        # creées dans le meme ordre que les lignes SO produit. Filtre
        # display_type pour exclure les eventuelles lignes section/note/arrondi.
        new_invoices = self.env['account.move'].sudo().search([
            ('insurance_sale_order_id', '=', self.id),
            ('id', 'not in', existing_ids),
        ])
        for invoice in new_invoices:
            inv_product_lines = invoice.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product'
            ).sorted('id')
            if len(inv_product_lines) != len(gift_flags):
                _logger.warning(
                    "is_gift: %d lignes facture vs %d lignes SO pour SO %s",
                    len(inv_product_lines), len(gift_flags), self.name,
                )
            for inv_line, is_gift in zip(inv_product_lines, gift_flags):
                if is_gift:
                    inv_line.is_gift = True

        return result
