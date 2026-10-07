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


class GymWorkoutTemplate(models.Model):
    _name = "gym.workout.template"
    _description = "Workout Template"
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
    duration_weeks = fields.Integer(string="Duration (Weeks)", required=True, default=4, tracking=True)
    description = fields.Text(string="Description", translate=True)
    line_ids = fields.One2many(
        "gym.workout.template.line",
        "template_id",
        string="Exercise Lines",
    )
    active = fields.Boolean(default=True)
    workout_plan_count = fields.Integer(compute="_compute_workout_plan_count")

    def _compute_workout_plan_count(self):
        plan_data = dict(
            self.env["gym.workout.plan"]
            .sudo()
            ._read_group(
                [("template_id", "in", self.ids)],
                ["template_id"],
                ["__count"],
            ),
        )
        for rec in self:
            rec.workout_plan_count = plan_data.get(rec, 0)

    @api.constrains("duration_weeks")
    def _check_duration(self):
        for rec in self:
            if rec.duration_weeks <= 0:
                raise ValidationError(_("Duration must be greater than 0."))

    def action_view_workout_plans(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Workout Plans"),
            "res_model": "gym.workout.plan",
            "view_mode": "list,form",
            "domain": [("template_id", "=", self.id)],
        }

    def unlink(self):
        for rec in self:
            if rec.workout_plan_count:
                raise UserError(
                    _(
                        'Workout Template "%s" cannot be deleted because it is used by existing Workout Plans. '
                        "Archive it instead.",
                    )
                    % rec.name,
                )
        return super().unlink()


class GymWorkoutTemplateLine(models.Model):
    _name = "gym.workout.template.line"
    _description = "Workout Template Line"
    _order = "sequence, day_of_week"
    _check_company_auto = True

    template_id = fields.Many2one(
        "gym.workout.template",
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
    sequence = fields.Integer(string="Sequence", default=10)
    day_of_week = fields.Selection(
        [
            ("monday", "Monday"),
            ("tuesday", "Tuesday"),
            ("wednesday", "Wednesday"),
            ("thursday", "Thursday"),
            ("friday", "Friday"),
            ("saturday", "Saturday"),
            ("sunday", "Sunday"),
        ],
        string="Day of Week",
        required=True,
    )
    exercise_id = fields.Many2one(
        "gym.exercise",
        string="Exercise",
        required=True,
        check_company=True,
    )
    exercise_category_id = fields.Many2one(
        related="exercise_id.category_id",
        string="Category",
        store=False,
    )
    exercise_equipment_ids = fields.Many2many(
        related="exercise_id.equipment_ids",
        string="Available Equipment",
        store=False,
    )
    equipment_id = fields.Many2one(
        "gym.equipment",
        string="Equipment",
        check_company=True,
        domain="[('id', 'in', exercise_equipment_ids)]",
    )
    sets = fields.Integer(string="Sets", default=3)
    reps = fields.Char(string="Reps", default="10-12", translate=True)
    rest_seconds = fields.Integer(string="Rest (seconds)", default=60)
    notes = fields.Char(string="Notes", translate=True)

    @api.constrains("sets")
    def _check_sets(self):
        for rec in self:
            if rec.sets <= 0:
                raise ValidationError(_("Sets must be greater than 0."))

    @api.onchange("exercise_id")
    def _onchange_exercise_id(self):
        if self.equipment_id and self.equipment_id not in self.exercise_id.equipment_ids:
            self.equipment_id = False
