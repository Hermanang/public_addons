# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class OpticalPec(models.Model):
    _inherit = 'optical.pec'

    def action_create_invoices(self):
        """Propager is_gift (SO line) → is_gift (invoice line) sur les factures."""
        self.ensure_one()
        order = self.sale_order_id.sudo()
        product_lines = order.order_line.filtered(
            lambda l: not l.display_type and l.product_uom_qty > 0,
        )
        gift_flags = [line.is_gift for line in product_lines]

        result = super().action_create_invoices()

        # Marquer is_gift sur les factures creées (assurance + TM)
        # sudo() : les droits utilisateur ont deja ete verifies en amont
        # Matching positionnel (zip) : suppose que PEC cree les lignes facture
        # dans le meme ordre que les lignes SO produit. Filtre display_type
        # pour exclure les eventuelles lignes section/note/arrondi.
        for invoice in (self.invoice_insurance_id | self.invoice_tm_id):
            if not invoice:
                continue
            inv_product_lines = invoice.sudo().invoice_line_ids.filtered(
                lambda l: l.display_type == 'product'
            ).sorted('id')
            if len(inv_product_lines) != len(gift_flags):
                _logger.warning(
                    "is_gift: %d lignes facture vs %d lignes SO pour PEC %s",
                    len(inv_product_lines), len(gift_flags), self.name,
                )
            for inv_line, is_gift in zip(inv_product_lines, gift_flags):
                if is_gift:
                    inv_line.is_gift = True

        return result
