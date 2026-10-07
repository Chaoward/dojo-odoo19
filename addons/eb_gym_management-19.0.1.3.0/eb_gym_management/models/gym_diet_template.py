# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

GOAL_TYPE_SELECTION = [
    ("weight_loss", "Weight Loss"),
    ("muscle_gain", "Muscle Gain"),
    ("strength", "Strength"),
    ("fitness", "General Fitness"),
    ("rehabilitation", "Rehabilitation"),
]


class GymDietTemplate(models.Model):
    _name = "gym.diet.template"
    _description = "Diet Template"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"
    _check_company_auto = True

    name = fields.Char(string="Template Name", required=True, tracking=True, translate=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        help="Leave empty to share this template across all branches.",
    )
    goal_type = fields.Selection(GOAL_TYPE_SELECTION, string="Goal Type", required=True, tracking=True)
    description = fields.Text(string="Description", translate=True)
    line_ids = fields.One2many(
        "gym.diet.template.line",
        "template_id",
        string="Meal Lines",
    )
    active = fields.Boolean(default=True)
    diet_plan_count = fields.Integer(compute="_compute_diet_plan_count")

    def _compute_diet_plan_count(self):
        plan_data = dict(
            self.env["gym.diet.plan"]
            .sudo()
            ._read_group(
                [("template_id", "in", self.ids)],
                ["template_id"],
                ["__count"],
            ),
        )
        for rec in self:
            rec.diet_plan_count = plan_data.get(rec, 0)

    def action_view_diet_plans(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Diet Plans"),
            "res_model": "gym.diet.plan",
            "view_mode": "list,form",
            "domain": [("template_id", "=", self.id)],
        }

    def unlink(self):
        for rec in self:
            if rec.diet_plan_count:
                raise UserError(
                    _(
                        'Diet Template "%s" cannot be deleted because it is used by existing Diet Plans. '
                        "Archive it instead.",
                    )
                    % rec.name,
                )
        return super().unlink()


class GymDietTemplateLine(models.Model):
    _name = "gym.diet.template.line"
    _description = "Diet Template Line"
    _order = "meal_type"
    _check_company_auto = True

    template_id = fields.Many2one(
        "gym.diet.template",
        string="Template",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="template_id.company_id",
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

    @api.constrains("quantity")
    def _check_quantity(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError(_("Quantity must be greater than 0."))
