# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    prescription_id = fields.Many2one(
        'optical.prescription',
        string="Ordonnance",
        domain="[('patient_id', '=', partner_id), ('state', '=', 'confirmed')]",
        tracking=True,
        copy=False,
        index='btree_not_null',
        ondelete='set null',
        check_company=True,
    )

    # --- Mesures ordonnance (related, lecture seule) ---
    prescription_od_sphere = fields.Float(related='prescription_id.od_sphere', string="SPH OD", readonly=True)
    prescription_od_cylinder = fields.Float(related='prescription_id.od_cylinder', string="CYL OD", readonly=True)
    prescription_od_axis = fields.Integer(related='prescription_id.od_axis', string="AXE OD", readonly=True)
    prescription_od_addition = fields.Float(related='prescription_id.od_addition', string="ADD OD", readonly=True)
    prescription_od_pd = fields.Float(related='prescription_id.od_pd', string="EP OD", readonly=True)
    prescription_og_sphere = fields.Float(related='prescription_id.og_sphere', string="SPH OG", readonly=True)
    prescription_og_cylinder = fields.Float(related='prescription_id.og_cylinder', string="CYL OG", readonly=True)
    prescription_og_axis = fields.Integer(related='prescription_id.og_axis', string="AXE OG", readonly=True)
    prescription_og_addition = fields.Float(related='prescription_id.og_addition', string="ADD OG", readonly=True)
    prescription_og_pd = fields.Float(related='prescription_id.og_pd', string="EP OG", readonly=True)
    prescription_pd_total = fields.Float(related='prescription_id.pd_total', string="EP Total", readonly=True)
    prescription_od_prism = fields.Float(related='prescription_id.od_prism', string="Prisme OD", readonly=True)
    prescription_od_prism_base = fields.Selection(related='prescription_id.od_prism_base', string="Base prisme OD", readonly=True)
    prescription_og_prism = fields.Float(related='prescription_id.og_prism', string="Prisme OG", readonly=True)
    prescription_og_prism_base = fields.Selection(related='prescription_id.og_prism_base', string="Base prisme OG", readonly=True)
    prescription_notes = fields.Text(related='prescription_id.notes', string="Observations", readonly=True)
    prescription_vision_type = fields.Selection(related='prescription_id.vision_type', string="Type de vision", readonly=True)
    prescription_measure_type = fields.Selection(related='prescription_id.measure_type', string="Type de prescription", readonly=True)
    prescription_measure_date = fields.Date(related='prescription_id.measure_date', string="Date de la mesure", readonly=True)

    policy_id = fields.Many2one(
        'optical.policy',
        string="Police d'assurance",
        domain="[('patient_id', '=', partner_id), ('state', '=', 'active')]",
        tracking=True,
        copy=False,
        index='btree_not_null',
        ondelete='set null',
    )
    amount_insurance = fields.Monetary(
        string="Part assurance",
        compute='_compute_insurance_amounts',
        store=True,
        currency_field='currency_id',
    )
    amount_patient = fields.Monetary(
        string="Ticket modérateur",
        compute='_compute_insurance_amounts',
        store=True,
        currency_field='currency_id',
    )
    has_insurance = fields.Boolean(
        string="Vente avec assurance",
        compute='_compute_has_insurance',
        store=True,
    )
    pec_id = fields.Many2one(
        'optical.pec',
        string="Prise en charge",
        readonly=True,
        copy=False,
    )
    pec_count = fields.Integer(
        string="Nombre PEC",
        compute='_compute_pec_count',
    )
    pec_state = fields.Selection(
        related='pec_id.state',
        string="État PEC",
    )

    @api.depends('policy_id')
    def _compute_has_insurance(self):
        for order in self:
            order.has_insurance = bool(order.policy_id)

    @api.depends('pec_id')
    def _compute_pec_count(self):
        for order in self:
            order.pec_count = 1 if order.pec_id else 0

    def action_confirm(self):
        """Bloquer la confirmation d'un devis assurance sans PEC."""
        for order in self:
            if order.has_insurance and not order.pec_id:
                raise UserError(
                    _("Veuillez créer une PEC avant de confirmer ce devis. "
                      "Une police d'assurance est sélectionnée mais aucune prise en charge n'a été créée.")
                )
        return super().action_confirm()

    def action_create_pec(self):
        """Créer une PEC depuis un devis ou une commande (FR31)."""
        self.ensure_one()
        if self.state not in ('draft', 'sent', 'sale'):
            raise UserError(_("Impossible de créer une PEC sur un devis/commande annulé(e)."))
        if not self.policy_id:
            raise UserError(_("Aucune police d'assurance sélectionnée sur cette commande."))
        if self.pec_id:
            raise UserError(_("Une PEC existe déjà pour cette commande."))
        if self.policy_id.state != 'active':
            raise UserError(_("La police d'assurance doit être active pour créer une PEC."))
        pec = self.env['optical.pec'].create({
            'sale_order_id': self.id,
            'policy_id': self.policy_id.id,
        })
        self.pec_id = pec.id
        return {
            'type': 'ir.actions.act_window',
            'name': _("Prise en charge"),
            'res_model': 'optical.pec',
            'res_id': pec.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_pec(self):
        """Ouvrir la PEC liée depuis le smart button."""
        self.ensure_one()
        if not self.pec_id:
            raise UserError(_("Aucune PEC liée à cette commande."))
        return {
            'type': 'ir.actions.act_window',
            'name': _("Prise en charge"),
            'res_model': 'optical.pec',
            'res_id': self.pec_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.depends('policy_id', 'order_line.amount_insurance_line', 'amount_total')
    def _compute_insurance_amounts(self):
        for order in self:
            if order.policy_id:
                total_insurance = sum(
                    line.amount_insurance_line
                    for line in order.order_line
                    if not line.display_type
                )
                order.amount_insurance = order.currency_id.round(total_insurance)
                order.amount_patient = order.currency_id.round(
                    order.amount_total - order.amount_insurance
                )
            else:
                order.amount_insurance = 0.0
                order.amount_patient = 0.0

    def write(self, vals):
        res = super().write(vals)
        if 'policy_id' in vals:
            for order in self.sudo():
                product_lines = order.order_line.filtered(
                    lambda l: not l.display_type and l.product_uom_qty > 0
                )
                if product_lines:
                    product_lines._update_estimation_amounts()
        return res

    @api.onchange('policy_id')
    def _onchange_policy_id_insurance(self):
        """Recalcule les estimations assurance par ligne quand la police change."""
        if self.order_line:
            product_lines = self.order_line.filtered(
                lambda l: not l.display_type and l.product_uom_qty > 0
            )
            product_lines._update_estimation_amounts()

    def _get_coverage_rule_for_line(self, line):
        """Retourne la règle de couverture applicable pour une ligne de commande."""
        policy = self.policy_id
        if not policy or not policy.plan_id:
            return self.env['optical.coverage.rule']
        optical_type = line.product_id.product_tmpl_id.optical_type
        if not optical_type:
            return self.env['optical.coverage.rule']
        rule = policy.plan_id.coverage_rule_ids.filtered(
            lambda r: r.product_category == optical_type
        )
        return rule[:1]

    def _get_line_coverage_rate(self, line):
        """Retourne le taux de couverture pour une ligne de commande (cascade 3 niveaux)."""
        policy = self.policy_id
        if not policy:
            return 0.0
        # Niveau 1 : règle par catégorie produit (plan)
        rule = self._get_coverage_rule_for_line(line)
        if rule:
            return rule.coverage_rate
        # Niveau 2 : taux par défaut du plan
        if policy.plan_id:
            return policy.plan_id.default_coverage_rate
        # Niveau 3 : taux de la police
        return policy.coverage_rate

    def _get_line_insurance_amount(self, line):
        """Calcule le montant assurance HT pour une ligne (utilisé par la facturation split)."""
        coverage_rate = self._get_line_coverage_rate(line)
        price_unit = line.price_subtotal / line.product_uom_qty if line.product_uom_qty else 0

        rule = self._get_coverage_rule_for_line(line)
        if rule and rule.reference_price > 0:
            covered_base = min(price_unit, rule.reference_price)
        else:
            covered_base = price_unit

        return covered_base * coverage_rate / 100.0 * line.product_uom_qty

    def _get_line_insurance_amount_ttc(self, line):
        """Calcule le montant assurance TTC pour une ligne (utilisé pour l'estimation commande)."""
        coverage_rate = self._get_line_coverage_rate(line)
        price_unit_ttc = line.price_total / line.product_uom_qty if line.product_uom_qty else 0

        rule = self._get_coverage_rule_for_line(line)
        if rule and rule.reference_price > 0:
            price_unit_ht = line.price_subtotal / line.product_uom_qty if line.product_uom_qty else 0
            if price_unit_ht > 0:
                capped_ratio = min(price_unit_ht, rule.reference_price) / price_unit_ht
                covered_base = price_unit_ttc * capped_ratio
            else:
                covered_base = 0
        else:
            covered_base = price_unit_ttc

        return covered_base * coverage_rate / 100.0 * line.product_uom_qty

    @api.depends('order_line.invoice_lines')
    def _get_invoiced(self):
        """Étendre le calcul des factures liées pour inclure les factures assurance.

        Les factures TM patient sont liées via sale_line_ids (mécanisme standard)
        et pilotent invoice_status / qty_invoiced — le patient est le vrai client.
        Les factures assurance ne le sont pas (pour ne pas doubler qty_invoiced),
        donc on les ajoute ici via insurance_sale_order_id pour le smart button.
        """
        super()._get_invoiced()
        for order in self:
            insurance_invoices = self.env['account.move'].search([
                ('insurance_sale_order_id', '=', order.id),
                ('is_insurance_invoice', '=', True),
                ('move_type', 'in', ('out_invoice', 'out_refund')),
            ])
            if insurance_invoices:
                order.invoice_ids = order.invoice_ids | insurance_invoices
                order.invoice_count = len(order.invoice_ids)

    @api.constrains('prescription_id')
    def _check_prescription_not_expired(self):
        for order in self.filtered('prescription_id'):
            if order.prescription_id.state == 'expired':
                raise ValidationError(
                    _("L'ordonnance %(name)s est expirée et ne peut pas être sélectionnée.",
                      name=order.prescription_id.name)
                )

    @api.constrains('prescription_id', 'partner_id')
    def _check_prescription_patient(self):
        for order in self.filtered('prescription_id'):
            if order.prescription_id.patient_id != order.partner_id:
                raise ValidationError(
                    _("L'ordonnance sélectionnée n'appartient pas au client du devis.")
                )

    @api.constrains('policy_id', 'partner_id')
    def _check_policy_patient(self):
        for order in self.filtered('policy_id'):
            if order.policy_id.patient_id != order.partner_id:
                raise ValidationError(
                    _("La police sélectionnée n'appartient pas au client du devis.")
                )
            if order.policy_id.state != 'active':
                raise ValidationError(
                    _("La police sélectionnée n'est pas active.")
                )

    def action_create_split_invoices(self):
        """Générer la facture assurance et le ticket modérateur (facturation split).

        Délègue à la PEC si elle existe et est approuvée (parcours obligatoire).
        """
        self.ensure_one()

        # --- Délégation PEC (parcours obligatoire pour dossiers assurance) ---
        if self.pec_id and self.pec_id.state == 'approved':
            return self.pec_id.action_create_invoices()
        if self.pec_id:
            raise UserError(_("La PEC doit être approuvée avant de générer les factures."))

        # --- Préconditions ---
        if self.state != 'sale':
            raise UserError(_("La commande doit être confirmée avant de générer les factures."))
        if not self.policy_id:
            raise UserError(_("Aucune police d'assurance sélectionnée sur cette commande."))
        existing = self.env['account.move'].search([
            ('insurance_sale_order_id', '=', self.id),
            ('move_type', '=', 'out_invoice'),
        ], limit=1)
        if existing:
            raise UserError(_("Les factures split ont déjà été générées pour cette commande."))

        # --- Lignes produit éligibles ---
        product_lines = self.order_line.filtered(
            lambda l: not l.display_type and l.product_uom_qty > 0,
        )
        if not product_lines:
            raise UserError(_("La commande ne contient aucune ligne produit facturable."))

        # --- Pré-calcul montants assurance par ligne (HT) ---
        currency = self.currency_id
        pec = self.pec_id
        use_manual = pec and pec.state in ('approved', 'invoiced') and pec.amount_insurance_approved > 0

        if use_manual:
            # Montants manuels : dériver HT depuis TTC via le ratio taxe
            line_ins_map = {}
            for line in product_lines:
                ins_ttc = line.amount_insurance_line
                ratio_ht = line.price_subtotal / line.price_total if line.price_total else 1.0
                line_ins_map[line.id] = currency.round(ins_ttc * ratio_ht)
        else:
            line_ins_map = {
                line.id: currency.round(self._get_line_insurance_amount(line))
                for line in product_lines
            }

        # --- Validation intégrité comptable NFR9 ---
        computed_ins_ht = sum(line_ins_map.values())
        computed_pat_ht = sum(
            currency.round(line.price_subtotal - line_ins_map[line.id])
            for line in product_lines
        )
        if abs(computed_ins_ht + computed_pat_ht - self.amount_untaxed) > 0.01:
            raise ValidationError(
                _("Erreur d'intégrité comptable : la somme HT des lignes assurance (%(ins)s) "
                  "+ TM (%(tm)s) ne correspond pas au montant HT commande (%(total)s).",
                  ins=computed_ins_ht, tm=computed_pat_ht, total=self.amount_untaxed)
            )

        # --- Cibles HT pour la correction d'arrondi ---
        target_ins_ht = computed_ins_ht
        target_pat_ht = currency.round(self.amount_untaxed - target_ins_ht)

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
        base_vals = self._prepare_invoice()
        base_vals.pop('invoice_line_ids', None)

        # --- Créer la facture assurance ---
        insurance_invoice = self.env['account.move'].create({
            **base_vals,
            'partner_id': self.policy_id.insurer_id.id,
            'is_insurance_invoice': True,
            'insurance_policy_id': self.policy_id.id,
            'insurance_sale_order_id': self.id,
            'invoice_line_ids': [fields.Command.create(v) for v in insurance_line_vals],
        })

        # --- Créer le ticket modérateur (si part patient > 0) ---
        if has_tm:
            tm_invoice = self.env['account.move'].create({
                **base_vals,
                'partner_id': self.partner_id.id,
                'is_tm_invoice': True,
                'insurance_policy_id': self.policy_id.id,
                'insurance_sale_order_id': self.id,
                'invoice_line_ids': [fields.Command.create(v) for v in tm_line_vals],
            })
        else:
            tm_invoice = self.env['account.move']

        _logger.info(
            "Facturation split générée pour commande %s : facture assurance %s, TM %s",
            self.name, insurance_invoice.name,
            tm_invoice.name if tm_invoice else 'aucun (couverture 100%)',
        )

        # --- Retourner action window montrant les factures ---
        invoices = insurance_invoice | tm_invoice
        return {
            'type': 'ir.actions.act_window',
            'name': _("Factures split"),
            'res_model': 'account.move',
            'domain': [('id', 'in', invoices.ids)],
            'view_mode': 'list,form' if tm_invoice else 'form',
            'res_id': insurance_invoice.id if not tm_invoice else False,
            'target': 'current',
            'context': {'default_move_type': 'out_invoice'},
        }


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    amount_insurance_line = fields.Monetary(
        string="Part assurance",
        store=True,
        currency_field='currency_id',
        default=0.0,
    )
    is_insurance_manual = fields.Boolean(
        string="Montant assurance ajusté manuellement",
        default=False,
    )
    amount_patient_line = fields.Monetary(
        string="Part patient ligne",
        compute='_compute_patient_line_amount',
        store=True,
        currency_field='currency_id',
    )

    @api.depends('price_total', 'amount_insurance_line')
    def _compute_patient_line_amount(self):
        for line in self:
            line.amount_patient_line = line.currency_id.round(
                line.price_total - line.amount_insurance_line
            ) if line.currency_id else line.price_total - line.amount_insurance_line

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines_to_update = lines.filtered(
            lambda l: not l.display_type and l.product_uom_qty > 0
            and l.order_id.policy_id and not l.amount_insurance_line
        )
        if lines_to_update:
            lines_to_update._update_estimation_amounts()
        return lines

    def _update_estimation_amounts(self):
        """Recalcule amount_insurance_line via la cascade Plan/Policy pour les lignes non manuelles."""
        for line in self:
            if line.display_type or line.product_uom_qty <= 0:
                line.amount_insurance_line = 0.0
                line.is_insurance_manual = False
                continue
            if line.order_id.policy_id:
                insurance_amount = line.order_id._get_line_insurance_amount_ttc(line)
                line.amount_insurance_line = line.currency_id.round(insurance_amount)
            else:
                line.amount_insurance_line = 0.0
            line.is_insurance_manual = False
