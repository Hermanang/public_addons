# -*- coding: utf-8 -*-
import base64
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class OpticalPec(models.Model):
    _name = 'optical.pec'
    _description = "Prise en charge"
    _inherit = ['mail.thread.main.attachment', 'mail.activity.mixin']
    _order = 'name desc'
    _check_company = True
    _rec_names_search = ['name', 'partner_ref']

    # === FIELDS === #
    name = fields.Char(
        string="Référence",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('Nouveau'),
        index='trigram',
    )
    partner_ref = fields.Char(
        string="Réf. organisme",
        copy=False,
        index='trigram',
        help="Référence de la prise en charge communiquée par l'organisme "
             "(numéro d'accord, référence IPM/mutuelle). Utilisée pour le "
             "rapprochement sur le bordereau.",
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string="Commande",
        required=True,
        index='btree_not_null',
        ondelete='restrict',
        check_company=True,
    )
    policy_id = fields.Many2one(
        'optical.policy',
        string="Police d'assurance",
        required=True,
        index='btree_not_null',
        ondelete='restrict',
        check_company=True,
    )
    patient_id = fields.Many2one(
        'res.partner',
        string="Patient",
        related='sale_order_id.partner_id',
        store=True,
        index='btree_not_null',
    )
    insurer_id = fields.Many2one(
        'res.partner',
        string="Assureur/IPM",
        related='policy_id.insurer_id',
        store=True,
        index='btree_not_null',
    )
    prescription_id = fields.Many2one(
        'optical.prescription',
        string="Ordonnance",
        related='sale_order_id.prescription_id',
        store=True,
    )
    amount_total = fields.Monetary(
        string="Total commande",
        related='sale_order_id.amount_total',
        currency_field='currency_id',
    )
    amount_insurance = fields.Monetary(
        string="Part assurance (estimation)",
        related='sale_order_id.amount_insurance',
        currency_field='currency_id',
    )
    amount_patient = fields.Monetary(
        string="Ticket modérateur (estimation)",
        related='sale_order_id.amount_patient',
        currency_field='currency_id',
    )
    # --- Montants approuvés (saisis après réponse mutuelle) ---
    amount_insurance_approved = fields.Monetary(
        string="Montant assurance approuvé",
        currency_field='currency_id',
        default=0.0,
        tracking=True,
        help="Montant global de prise en charge communiqué par la mutuelle/IPM.",
    )
    amount_patient_approved = fields.Monetary(
        string="Part patient approuvée",
        compute='_compute_amount_patient_approved',
        store=True,
        currency_field='currency_id',
    )
    state = fields.Selection(
        [
            ('draft', 'Brouillon'),
            ('submitted', 'Soumise'),
            ('approved', 'Approuvé'),
            ('refused', 'Refusé'),
            ('invoiced', 'Facturé'),
        ],
        string="État",
        default='draft',
        required=True,
        tracking=True,
        index=True,
    )
    payment_status = fields.Selection(
        [
            ('none', 'Aucune facture'),
            ('not_paid', 'Non payée'),
            ('partial', 'Partiellement payée'),
            ('paid', 'Payée'),
        ],
        string="Statut paiement",
        compute='_compute_payment_status',
        store=True,
    )
    date_create = fields.Date(
        string="Date de création",
        default=fields.Date.context_today,
        readonly=True,
        copy=False,
    )
    date_approved = fields.Date(
        string="Date d'approbation",
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string="Société",
        related='sale_order_id.company_id',
        store=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string="Devise",
        related='company_id.currency_id',
        store=True,
    )
    active = fields.Boolean(default=True)
    invoice_insurance_id = fields.Many2one(
        'account.move',
        string="Facture assurance",
        readonly=True,
        copy=False,
        check_company=True,
    )
    invoice_tm_id = fields.Many2one(
        'account.move',
        string="Facture ticket modérateur",
        readonly=True,
        copy=False,
        check_company=True,
    )
    notes = fields.Text(string="Observations")

    _sql_constraints = [
        ('sale_order_unique', 'unique(sale_order_id)',
         "Une seule PEC par commande."),
    ]

    # === COMPUTED METHODS === #
    @api.depends('amount_total', 'amount_insurance_approved')
    def _compute_amount_patient_approved(self):
        for pec in self:
            if pec.amount_total:
                pec.amount_patient_approved = pec.currency_id.round(
                    pec.amount_total - pec.amount_insurance_approved
                )
            else:
                pec.amount_patient_approved = 0.0

    @api.depends('invoice_insurance_id.payment_state', 'invoice_tm_id.payment_state')
    def _compute_payment_status(self):
        for pec in self:
            if not pec.invoice_insurance_id and not pec.invoice_tm_id:
                pec.payment_status = 'none'
                continue
            invoices = pec.invoice_insurance_id | pec.invoice_tm_id
            payment_states = invoices.mapped('payment_state')
            if all(s == 'paid' for s in payment_states):
                pec.payment_status = 'paid'
            elif all(s == 'not_paid' for s in payment_states):
                pec.payment_status = 'not_paid'
            else:
                pec.payment_status = 'partial'

    @api.depends('name', 'partner_ref')
    def _compute_display_name(self):
        for pec in self:
            name = pec.name
            if pec.partner_ref:
                name += ' (' + pec.partner_ref + ')'
            pec.display_name = name

    # === ONCHANGE === #
    @api.onchange('amount_insurance_approved')
    def _onchange_amount_insurance_approved(self):
        """AC#5 : réinitialiser les flags manuels et redistribuer automatiquement."""
        if self.state != 'approved' or not self.amount_insurance_approved:
            return
        order = self.sale_order_id.sudo()
        product_lines = order.order_line.filtered(
            lambda l: not l.display_type and l.product_uom_qty > 0
        )
        if product_lines:
            product_lines.write({'is_insurance_manual': False})
        self.action_distribute_insurance()

    # === CONSTRAINTS === #
    @api.constrains('amount_insurance_approved')
    def _check_amount_insurance_approved(self):
        for pec in self:
            if pec.amount_insurance_approved < 0:
                raise ValidationError(
                    _("Le montant assurance approuvé ne peut pas être négatif.")
                )
            if pec.amount_total and pec.amount_insurance_approved > pec.amount_total:
                raise ValidationError(
                    _("Le montant assurance approuvé (%(amount)s) ne peut pas dépasser "
                      "le total commande (%(total)s).",
                      amount=pec.amount_insurance_approved, total=pec.amount_total)
                )

    # === CRUD OVERRIDES === #
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('Nouveau'):
                vals['name'] = self.env['ir.sequence'].next_by_code('optical.pec') or _('Nouveau')
        return super().create(vals_list)

    def unlink(self):
        raise UserError(_("La suppression n'est pas autorisée. Utilisez l'archivage."))

    # === ACTION METHODS === #
    def action_submit(self):
        """Soumettre la PEC pour approbation (draft → submitted)."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Seule une PEC en brouillon peut être soumise."))
        if self.policy_id.state != 'active':
            raise UserError(_("La police d'assurance n'est pas active."))
        self.write({'state': 'submitted'})

    def action_approve(self):
        """Approuver la PEC (submitted → approved). Réservé au responsable."""
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError(_("Seule une PEC soumise peut être approuvée."))
        if not self.env.user.has_group('optical.group_optical_manager'):
            raise UserError(_("Seul un responsable optique peut approuver une PEC."))
        self.write({
            'state': 'approved',
            'date_approved': fields.Date.context_today(self),
        })

    def action_refuse(self):
        """Refuser la PEC (submitted → refused). Réservé au responsable."""
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError(_("Seule une PEC soumise peut être refusée."))
        if not self.env.user.has_group('optical.group_optical_manager'):
            raise UserError(_("Seul un responsable optique peut refuser une PEC."))
        self.write({'state': 'refused'})

    def action_reset_draft(self):
        """Remettre la PEC en brouillon (refused → draft). Réservé au responsable (FR33)."""
        self.ensure_one()
        if self.state != 'refused':
            raise UserError(_("Seule une PEC refusée peut être remise en brouillon."))
        if not self.env.user.has_group('optical.group_optical_manager'):
            raise UserError(_("Seul un responsable optique peut remettre une PEC en brouillon."))
        self.write({'state': 'draft', 'date_approved': False})

    def action_reset_to_submitted(self):
        """Remettre la PEC en soumis (approved → submitted). Réservé au responsable."""
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_("Seule une PEC approuvée peut être remise en soumis."))
        if not self.env.user.has_group('optical.group_optical_manager'):
            raise UserError(_("Seul un responsable optique peut remettre une PEC en soumis."))
        if self.invoice_insurance_id or self.invoice_tm_id:
            raise UserError(
                _("Impossible de remettre en soumis : des factures ont déjà été générées. "
                  "Annulez les factures d'abord.")
            )
        self.write({
            'state': 'submitted',
            'date_approved': False,
            'amount_insurance_approved': 0,
        })
        # Réinitialiser les montants par ligne à l'estimation cascade
        order = self.sale_order_id.sudo()
        product_lines = order.order_line.filtered(
            lambda l: not l.display_type and l.product_uom_qty > 0
        )
        if product_lines:
            product_lines._update_estimation_amounts()

    def action_distribute_insurance(self):
        """Distribuer amount_insurance_approved proportionnellement sur les lignes du devis."""
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_("La distribution n'est possible que sur une PEC approuvée."))

        order = self.sale_order_id.sudo()
        product_lines = order.order_line.filtered(
            lambda l: not l.display_type and l.product_uom_qty > 0
        )
        if not product_lines:
            return

        total_approved = self.amount_insurance_approved
        if total_approved <= 0:
            # Reset toutes les lignes à 0
            product_lines.write({'amount_insurance_line': 0, 'is_insurance_manual': False})
            return

        # Somme des lignes manuelles (verrouillées)
        manual_lines = product_lines.filtered('is_insurance_manual')
        auto_lines = product_lines - manual_lines
        manual_total = sum(l.amount_insurance_line for l in manual_lines)

        reliquat = self.currency_id.round(total_approved - manual_total)
        if reliquat < -0.01:
            raise UserError(
                _("La somme des lignes manuelles (%(manual)s) dépasse le montant approuvé (%(total)s).",
                  manual=manual_total, total=total_approved)
            )

        if not auto_lines:
            return

        # Répartition proportionnelle sur les lignes non manuelles
        total_auto_price = sum(l.price_total for l in auto_lines)
        if total_auto_price <= 0:
            return

        distributed = 0.0
        sorted_lines = list(auto_lines.sorted('id'))
        for line in sorted_lines[:-1]:
            amount = self.currency_id.round(reliquat * line.price_total / total_auto_price)
            line.write({'amount_insurance_line': amount, 'is_insurance_manual': False})
            distributed += amount

        # Dernière ligne : correction d'arrondi
        last_amount = self.currency_id.round(reliquat - distributed)
        sorted_lines[-1].write({'amount_insurance_line': last_amount, 'is_insurance_manual': False})

    def action_create_invoices(self):
        """Générer les factures depuis la PEC approuvée (ADR-1, FR34).

        Crée 1 ou 2 account.move selon la couverture :
        - Facture assurance (partenaire = IPM) — toujours créée
        - Ticket modérateur (partenaire = patient) — uniquement si part patient > 0
        Les taxes sont héritées des lignes de commande.
        """
        self.ensure_one()

        # --- Préconditions ---
        if self.state != 'approved':
            raise UserError(_("Seule une PEC approuvée peut générer les factures."))
        if not self.env.user.has_group('optical.group_optical_manager'):
            raise UserError(_("Seul un responsable optique peut générer les factures."))
        if self.invoice_insurance_id or self.invoice_tm_id:
            raise UserError(_("Les factures ont déjà été générées pour cette PEC."))

        order = self.sale_order_id.sudo()
        if order.state != 'sale':
            raise UserError(_("La commande doit être confirmée avant de générer les factures."))
        if self.policy_id.state != 'active':
            raise UserError(_("La police d'assurance n'est pas active."))

        # --- Lignes produit éligibles ---
        product_lines = order.order_line.filtered(
            lambda l: not l.display_type and l.product_uom_qty > 0,
        )
        if not product_lines:
            raise UserError(_("La commande ne contient aucune ligne produit facturable."))

        # --- Pré-calcul montants assurance par ligne (HT) ---
        currency = order.currency_id
        use_manual = self.amount_insurance_approved > 0

        if use_manual:
            # Validation intégrité montants manuels
            line_total_ttc = sum(l.amount_insurance_line for l in product_lines)
            if abs(line_total_ttc - self.amount_insurance_approved) > 0.01:
                raise ValidationError(
                    _("La somme des montants par ligne (%(lines)s) ne correspond pas au "
                      "montant approuvé (%(approved)s). Utilisez le bouton 'Répartir'.",
                      lines=line_total_ttc, approved=self.amount_insurance_approved)
                )
            # Montants manuels : dériver HT depuis TTC via le ratio taxe
            line_ins_map = {}
            for line in product_lines:
                ins_ttc = line.amount_insurance_line
                ratio_ht = line.price_subtotal / line.price_total if line.price_total else 1.0
                line_ins_map[line.id] = currency.round(ins_ttc * ratio_ht)
        else:
            # Mode estimation cascade (rétrocompatible)
            line_ins_map = {
                line.id: currency.round(order._get_line_insurance_amount(line))
                for line in product_lines
            }

        # --- Validation intégrité comptable NFR9 ---
        computed_ins_ht = sum(line_ins_map.values())
        computed_pat_ht = sum(
            currency.round(line.price_subtotal - line_ins_map[line.id])
            for line in product_lines
        )
        if abs(computed_ins_ht + computed_pat_ht - order.amount_untaxed) > 0.01:
            raise ValidationError(
                _("Erreur d'intégrité comptable : la somme HT des lignes assurance (%(ins)s) "
                  "+ TM (%(tm)s) ne correspond pas au montant HT commande (%(total)s).",
                  ins=computed_ins_ht, tm=computed_pat_ht, total=order.amount_untaxed)
            )

        # --- Cibles HT pour la correction d'arrondi ---
        target_ins_ht = computed_ins_ht
        target_pat_ht = currency.round(order.amount_untaxed - target_ins_ht)

        # --- Préparer les lignes de facture (prix HT, taxes du produit) ---
        has_tm = computed_pat_ht > 0.01
        insurance_line_vals = []
        tm_line_vals = []
        insurance_line_amounts = []
        tm_line_amounts = []

        for line in product_lines:
            line_ins_ht = line_ins_map[line.id]

            ins_price_ht = currency.round(line_ins_ht / line.product_uom_qty)

            # Ratio TTC/HT : convertit le prix HT dans l'espace attendu par Odoo.
            # Quand la taxe est en mode price_include (ex: TVA 18% TTC), Odoo
            # interprète price_unit comme TTC et re-déduit la taxe. Sans cette
            # conversion, le HT réel serait inférieur au HT voulu (double déduction).
            if line.price_subtotal and abs(line.price_subtotal) > 0.01:
                ttc_ratio = line.price_total / line.price_subtotal
            else:
                ttc_ratio = 1.0
            ins_price = currency.round(ins_price_ht * ttc_ratio)

            # Taxes explicites depuis la ligne commande (évite les taxes par défaut du produit)
            tax_ids = [fields.Command.set(line.tax_id.ids)]

            # Pas de sale_line_ids sur les lignes assurance pour ne pas doubler qty_invoiced
            insurance_line_vals.append({
                'product_id': line.product_id.id,
                'name': line.product_id.name,
                'quantity': line.product_uom_qty,
                'product_uom_id': line.product_uom.id,
                'price_unit': ins_price,
                'tax_ids': tax_ids,
            })
            insurance_line_amounts.append(ins_price_ht * line.product_uom_qty)

            if has_tm:
                line_pat_ht = currency.round(line.price_subtotal - line_ins_ht)
                tm_price_ht = currency.round(line_pat_ht / line.product_uom_qty)
                tm_price = currency.round(tm_price_ht * ttc_ratio)
                tm_line_vals.append({
                    'product_id': line.product_id.id,
                    'name': line.product_id.name,
                    'quantity': line.product_uom_qty,
                    'product_uom_id': line.product_uom.id,
                    'price_unit': tm_price,
                    'tax_ids': tax_ids,
                    'sale_line_ids': [fields.Command.link(line.id)],
                })
                tm_line_amounts.append(tm_price_ht * line.product_uom_qty)

        # --- Correction d'arrondi sur la ligne la mieux adaptée ---
        # Chercher la meilleure ligne de correction : préférer une ligne avec
        # montant non nul et qté=1 pour éviter l'amplification d'arrondi
        # quand diff n'est pas divisible par la quantité (ex: diff=-1, qty=2
        # → round(-0.5)=-1 par unité → correction réelle=-2 au lieu de -1).
        corr_idx = len(product_lines) - 1
        for i in range(len(product_lines) - 1, -1, -1):
            line = product_lines[i]
            if line.price_total and abs(line.price_total) > 0.01:
                corr_idx = i
                if line.product_uom_qty == 1:
                    break
        corr_line = product_lines[corr_idx]
        corr_qty = corr_line.product_uom_qty
        corr_ratio = (corr_line.price_total / corr_line.price_subtotal
                      if corr_line.price_subtotal and abs(corr_line.price_subtotal) > 0.01
                      else 1.0)

        if insurance_line_vals:
            total_ins = sum(insurance_line_amounts)
            diff_ins = currency.round(target_ins_ht - total_ins)
            if diff_ins:
                target_line_ht = insurance_line_amounts[corr_idx] + diff_ins
                new_price_ht = currency.round(target_line_ht / corr_qty)
                insurance_line_vals[corr_idx]['price_unit'] = currency.round(
                    new_price_ht * corr_ratio)

        if tm_line_vals:
            total_tm = sum(tm_line_amounts)
            diff_tm = currency.round(target_pat_ht - total_tm)
            if diff_tm:
                target_line_ht = tm_line_amounts[corr_idx] + diff_tm
                new_price_ht = currency.round(target_line_ht / corr_qty)
                tm_line_vals[corr_idx]['price_unit'] = currency.round(
                    new_price_ht * corr_ratio)

        # --- Préparer les vals de base via le standard Odoo ---
        # _prepare_invoice() fournit invoice_user_id, team_id, currency_id,
        # company_id, fiscal_position_id, etc. automatiquement.
        base_vals = order._prepare_invoice()
        base_vals.pop('invoice_line_ids', None)  # on gère nos propres lignes

        # --- Créer la facture assurance (sudo : droits vérifiés en amont) ---
        AccountMove = self.env['account.move'].sudo()
        insurance_invoice = AccountMove.create({
            **base_vals,
            'partner_id': self.insurer_id.id,
            'is_insurance_invoice': True,
            'insurance_policy_id': self.policy_id.id,
            'insurance_sale_order_id': order.id,
            'pec_id': self.id,
            'invoice_line_ids': [fields.Command.create(v) for v in insurance_line_vals],
        })

        # --- Créer le ticket modérateur (si part patient > 0) ---
        if has_tm:
            tm_invoice = AccountMove.create({
                **base_vals,
                'partner_id': self.patient_id.id,
                'is_tm_invoice': True,
                'insurance_policy_id': self.policy_id.id,
                'insurance_sale_order_id': order.id,
                'pec_id': self.id,
                'invoice_line_ids': [fields.Command.create(v) for v in tm_line_vals],
            })
        else:
            tm_invoice = self.env['account.move']  # recordset vide

        # --- Mettre à jour la PEC ---
        vals = {
            'state': 'invoiced',
            'invoice_insurance_id': insurance_invoice.id,
        }
        if tm_invoice:
            vals['invoice_tm_id'] = tm_invoice.id
        self.write(vals)

        if tm_invoice:
            _logger.info(
                "Facturation split PEC %s : facture assurance %s, TM %s",
                self.name, insurance_invoice.name, tm_invoice.name,
            )
            self.message_post(body=_(
                "Factures générées : %(ins)s (assurance) et %(tm)s (ticket modérateur).",
                ins=insurance_invoice.name, tm=tm_invoice.name,
            ))
        else:
            _logger.info(
                "Facturation PEC %s : facture assurance %s (couverture 100%%, pas de TM)",
                self.name, insurance_invoice.name,
            )
            self.message_post(body=_(
                "Facture générée : %(ins)s (assurance). Couverture 100%%, pas de ticket modérateur.",
                ins=insurance_invoice.name,
            ))

        # --- Retourner action window montrant les factures ---
        invoices = insurance_invoice | tm_invoice
        return {
            'type': 'ir.actions.act_window',
            'name': _("Factures PEC"),
            'res_model': 'account.move',
            'domain': [('id', 'in', invoices.ids)],
            'view_mode': 'list,form' if tm_invoice else 'form',
            'res_id': insurance_invoice.id if not tm_invoice else False,
            'target': 'current',
            'context': {'default_move_type': 'out_invoice'},
        }

    def action_send_to_insurer(self):
        """Ouvrir le wizard d'envoi email à l'assureur (FR64).

        Valide que l'assureur a un email, charge le template,
        attache le PDF ordonnance si disponible, puis ouvre
        mail.compose.message pré-rempli.
        """
        self.ensure_one()
        if not self.insurer_id.email:
            raise UserError(
                _("L'assureur '%(name)s' n'a pas d'adresse email configurée. "
                  "Veuillez configurer l'email sur la fiche du contact avant l'envoi.",
                  name=self.insurer_id.name)
            )
        template = self.env.ref(
            'optical.email_template_pec_request', raise_if_not_found=False,
        )
        ctx = {
            'default_model': 'optical.pec',
            'default_res_ids': self.ids,
            'default_template_id': template and template.id or False,
            'default_composition_mode': 'comment',
            'mark_pec_submitted': True,
            'force_email': True,
        }
        # Attacher le PDF du devis si le rapport existe
        attachment_ids = []
        try:
            report = self.env.ref('sale.action_report_saleorder')
            pdf_content, _content_type = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
                report, self.sale_order_id.ids,
            )
            attachment = self.env['ir.attachment'].create({
                'name': '%s.pdf' % self.sale_order_id.name,
                'type': 'binary',
                'datas': base64.b64encode(pdf_content),
                'res_model': 'optical.pec',
                'res_id': self.id,
                'mimetype': 'application/pdf',
            })
            attachment_ids.append(attachment.id)
        except Exception:
            _logger.warning(
                "Rapport devis non disponible pour la PEC %s, envoi sans PDF", self.name,
            )

        # Attacher le PDF ordonnance si pièce jointe existante
        if self.prescription_id and self.prescription_id.message_main_attachment_id:
            attachment_ids.append(self.prescription_id.message_main_attachment_id.id)

        # Attacher la carte police si pièce jointe principale existante
        if self.policy_id.message_main_attachment_id:
            attachment_ids.append(self.policy_id.message_main_attachment_id.id)

        if attachment_ids:
            ctx['default_attachment_ids'] = [fields.Command.set(list(set(attachment_ids)))]

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }

    def _message_post_after_hook(self, message, msg_values):
        """Transition draft → submitted après envoi email via wizard (FR64)."""
        res = super()._message_post_after_hook(message, msg_values)
        if self.env.context.get('mark_pec_submitted') and self.state == 'draft':
            self.write({'state': 'submitted'})
            _logger.info(
                "PEC %s passée en soumise après envoi email à l'assureur", self.name,
            )
        return res

    def action_view_invoice_insurance(self):
        """Ouvrir la facture assurance liée."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Facture assurance"),
            'res_model': 'account.move',
            'res_id': self.invoice_insurance_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_invoice_tm(self):
        """Ouvrir le ticket modérateur lié."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Ticket modérateur"),
            'res_model': 'account.move',
            'res_id': self.invoice_tm_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
