# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'

    @api.model_create_multi
    def create(self, vals_list):
        complaint_type = self.env.ref(
            'optical_helpdesk.type_complaint',
            raise_if_not_found=False,
        )
        for vals in vals_list:
            if vals.get('number', '/') == '/' and complaint_type \
                    and vals.get('type_id') == complaint_type.id:
                num = self.env['ir.sequence'].next_by_code(
                    'optical.helpdesk.ticket.sequence'
                )
                if num:
                    vals['number'] = num
        return super().create(vals_list)

    partner_phone = fields.Char(
        related='partner_id.phone',
        string="Téléphone",
        readonly=False,
    )

    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        readonly=True,
    )

    product_id_domain = fields.Char(
        compute='_compute_product_id_domain',
        help="Domaine dynamique pour product_id : limite aux produits des "
             "sale_order_ids liés s'il y en a, sinon aux produits sale_ok. "
             "Évite de charger tous les produits en m2m à chaque ouverture "
             "de form (gain de perf significatif sur grosses bases).",
    )

    product_id = fields.Many2one(
        comodel_name='product.product',
        string="Produit concerné",
    )

    optical_type = fields.Selection(
        related='product_id.product_tmpl_id.optical_type',
        string="Type produit",
        store=True,
    )

    purchase_price = fields.Monetary(
        string="Prix d'achat",
        currency_field='currency_id',
        compute='_compute_purchase_price',
        store=True,
        readonly=False,
    )

    internal_diagnostic = fields.Html(
        string="Diagnostic interne",
    )

    proposed_solution = fields.Selection(
        selection=[
            ('reprise_reglage', "Reprise-réglage"),
            ('remplacement_verre', "Remplacement verre"),
            ('remplacement_monture', "Remplacement monture"),
            ('remboursement', "Remboursement"),
            ('rejet', "Rejet"),
        ],
        string="Solution proposée",
    )

    cause_identified = fields.Selection(
        selection=[
            ('atelier', "Atelier"),
            ('manipulation_client', "Manipulation client"),
            ('fournisseur', "Fournisseur"),
            ('autre', "Autre"),
        ],
        string="Cause identifiée",
    )

    refund_amount = fields.Monetary(
        string="Montant du remboursement",
        currency_field='currency_id',
    )

    complaint_motive_ids = fields.Many2many(
        comodel_name='helpdesk.complaint.motive',
        relation='helpdesk_ticket_complaint_motive_rel',
        column1='ticket_id',
        column2='motive_id',
        string="Motifs de réclamation",
    )

    def _is_motive_checked(self, motive_xmlid):
        """Helper QWeb : retourne True si le motif identifié par xmlid est
        attaché au ticket.

        Robuste à la suppression du motif depuis l'UI (admin) : si l'xmlid
        n'existe plus, retourne False sans crasher (évite ValueError sur
        env.ref dans le rapport QWeb).
        """
        self.ensure_one()
        motive = self.env.ref(motive_xmlid, raise_if_not_found=False)
        return bool(motive) and motive in self.complaint_motive_ids

    @api.depends('sale_order_ids', 'sale_order_ids.order_line.product_id')
    def _compute_product_id_domain(self):
        for ticket in self:
            if ticket.sale_order_ids:
                product_ids = ticket.sale_order_ids.mapped('order_line.product_id').ids
                ticket.product_id_domain = repr([('id', 'in', product_ids)])
            else:
                ticket.product_id_domain = repr([('sale_ok', '=', True)])

    @api.depends('product_id', 'sale_order_ids', 'sale_order_ids.order_line.price_total')
    def _compute_purchase_price(self):
        """Auto-remplit purchase_price depuis la ligne de SO matchant product_id.

        Comportement "smart default" :
        - Si product_id présent ET trouvé dans une SO liée → écrase avec
          line.price_total (TTC)
        - Sinon, si purchase_price est déjà non-zero, on ne touche pas
          (préserve la saisie manuelle)
        - Sinon, met à 0.0 (initialisation)

        Note : ce comportement signifie qu'une saisie manuelle peut être
        écrasée si l'utilisateur change ensuite product_id ou sale_order_ids.
        C'est volontaire pour garder cohérent avec la commande liée.
        """
        for ticket in self:
            if ticket.product_id and ticket.sale_order_ids:
                line = ticket.sale_order_ids.mapped('order_line').filtered(
                    lambda l, pid=ticket.product_id: l.product_id == pid
                )[:1]
                if line:
                    ticket.purchase_price = line.price_total
                    continue
            if not ticket.purchase_price:
                ticket.purchase_price = 0.0
