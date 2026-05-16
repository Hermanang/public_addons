from odoo import _, fields, models
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval


class GamificationGoal(models.Model):
    _inherit = "gamification.goal"

    definition_action_id = fields.Many2one(
        related="definition_id.action_id",
        string="Definition Action",
        readonly=True,
    )

    def _parse_domain(self, domain_str):
        if not domain_str:
            return []
        if isinstance(domain_str, str):
            return safe_eval(domain_str, {"uid": self.env.uid})
        if isinstance(domain_str, (list, tuple)):
            return list(domain_str)
        return []

    def _goal_records_domain(self):
        self.ensure_one()
        definition = self.definition_id
        if definition.computation_mode not in ("count", "sum"):
            return []
        base = self._parse_domain(definition.domain)
        dom = list(base) if base else []
        if definition.batch_mode and definition.batch_distinctive_field:
            val = safe_eval(
                definition.batch_user_expression or "False",
                {"user": self.user_id},
            )
            dom.append((definition.batch_distinctive_field.name, "=", val))
        field_date = definition.field_date_id.name if definition.field_date_id else False
        if field_date and self.start_date:
            dom.append((field_date, ">=", self.start_date))
        if field_date and self.end_date:
            dom.append((field_date, "<=", self.end_date))
        return dom

    def _clean_action_context(self, ctx):
        if not ctx:
            return {}
        if isinstance(ctx, str):
            ctx = safe_eval(ctx, {"uid": self.env.uid})
        if not isinstance(ctx, dict):
            return {}
        return {
            k: v
            for k, v in ctx.items()
            if not (isinstance(k, str) and k.startswith("search_default_"))
        }

    def get_action(self):
        self.ensure_one()
        if self.definition_id.action_id:
            action = self.definition_id.action_id.read()[0]
            action_domain = self._parse_domain(action.get("domain"))
            scoped = self._goal_records_domain()
            action["domain"] = expression.AND([action_domain, scoped])
            ctx_clean = self._clean_action_context(action.get("context"))
            if ctx_clean:
                action["context"] = ctx_clean
            else:
                del action["context"]
            if self.definition_id.res_id_field:
                user = self.user_id
                action["res_id"] = safe_eval(
                    self.definition_id.res_id_field, {"user": user}
                )
                action["views"] = [
                    (vid, mode)
                    for vid, mode in action.get("views", [])
                    if mode == "form"
                ] or action.get("views", [])
            return action
        if self.computation_mode == "manually":
            return super().get_action()
        return {"type": "ir.actions.act_window_close"}
