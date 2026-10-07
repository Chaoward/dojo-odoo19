# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class GymDietPlan(models.Model):
    _name = "gym.diet.plan"
    _description = "Diet Plan"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    _check_company_auto = True

    name = fields.Char(string="Reference", readonly=True, copy=False, default="New")
    membership_id = fields.Many2one("gym.membership", string="Membership", required=True, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="membership_id.company_id",
        store=True,
        index=True,
        readonly=True,
    )
    health_assessment_id = fields.Many2one(
        "gym.health.assessment",
        string="Health Assessment",
        required=True,
        tracking=True,
    )
    template_id = fields.Many2one(
        "gym.diet.template",
        string="Diet Template",
        required=True,
        tracking=True,
    )
    nutritionist_id = fields.Many2one(
        "hr.employee",
        string="Nutritionist",
        required=True,
        tracking=True,
        domain=[("is_nutritionist", "=", True)],
        check_company=True,
    )
    start_date = fields.Date(string="Start Date", required=True, default=fields.Date.today)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("completed", "Completed"),
            ("revised", "Revised"),
        ],
        string="Status",
        default="draft",
        tracking=True,
        copy=False,
    )
    line_ids = fields.One2many("gym.diet.plan.line", "plan_id", string="Meal Lines")
    previous_plan_id = fields.Many2one(
        "gym.diet.plan",
        string="Previous Version",
        copy=False,
    )

    @api.onchange("template_id")
    def _onchange_template_id(self):
        if self.template_id:
            self.line_ids = [(5, 0, 0)]
            self.line_ids = self._lines_from_template(self.template_id)

    def _lines_from_template(self, template):
        return [
            (
                0,
                0,
                {
                    "meal_type": tl.meal_type,
                    "food_id": tl.food_id.id,
                    "quantity": tl.quantity,
                    "uom": tl.uom,
                    "notes": tl.notes,
                },
            )
            for tl in template.line_ids
        ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("gym.diet.plan") or "New"
            if vals.get("template_id") and not vals.get("line_ids"):
                template = self.env["gym.diet.template"].browse(vals["template_id"])
                vals["line_ids"] = self._lines_from_template(template)
        return super().create(vals_list)

    def unlink(self):
        for rec in self:
            if rec.state in ("active", "completed"):
                raise UserError(
                    _('Diet Plan "%s" cannot be deleted because it is %s. ' "Keep it for history instead.")
                    % (rec.name, rec.state),
                )
        return super().unlink()

    def copy(self, default=None):
        raise UserError(_("Diet Plans cannot be duplicated. Create a new plan from a Health Assessment instead."))

    def action_activate(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Cannot activate a Diet Plan with no Meal Lines."))
            rec.state = "active"

    def action_complete(self):
        self.state = "completed"

    def action_view_previous(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Previous Version"),
            "res_model": "gym.diet.plan",
            "view_mode": "form",
            "res_id": self.previous_plan_id.id,
        }


class GymDietPlanLine(models.Model):
    _name = "gym.diet.plan.line"
    _description = "Diet Plan Line"
    _order = "meal_type"
    _check_company_auto = True

    plan_id = fields.Many2one("gym.diet.plan", string="Plan", required=True, ondelete="cascade")
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="plan_id.company_id",
        store=True,
        index=True,
        readonly=True,
    )
    meal_type = fields.Selection(
        [
            ("breakfast", "Breakfast"),
            ("mid_morning", "Mid-Morning Snack"),
            ("lunch", "Lunch"),
            ("evening_snack", "Evening Snack"),
            ("dinner", "Dinner"),
        ],
        string="Meal Type",
        required=True,
    )
    food_id = fields.Many2one("gym.food", string="Food Item", required=True, check_company=True)
    quantity = fields.Float(string="Quantity", default=100.0)
    uom = fields.Selection(
        [
            ("g", "g"),
            ("ml", "ml"),
            ("piece", "Piece"),
            ("cup", "Cup"),
        ],
        string="Unit",
        default="g",
    )
    notes = fields.Char(string="Notes", translate=True)
