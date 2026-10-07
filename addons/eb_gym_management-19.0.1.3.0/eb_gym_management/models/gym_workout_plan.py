# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class GymWorkoutPlan(models.Model):
    _name = "gym.workout.plan"
    _description = "Workout Plan"
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
        "gym.workout.template",
        string="Template",
        required=True,
        tracking=True,
    )
    trainer_id = fields.Many2one(
        "hr.employee",
        string="Trainer",
        required=True,
        tracking=True,
        domain=[("is_trainer", "=", True)],
        check_company=True,
    )
    start_date = fields.Date(string="Start Date", required=True, default=fields.Date.today)
    end_date = fields.Date(string="End Date", compute="_compute_end_date", store=True)
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
    line_ids = fields.One2many("gym.workout.plan.line", "plan_id", string="Exercise Lines")
    previous_plan_id = fields.Many2one(
        "gym.workout.plan",
        string="Previous Version",
        copy=False,
    )
    goal_mismatch = fields.Boolean(compute="_compute_goal_mismatch", store=False)

    @api.depends("start_date", "template_id.duration_weeks")
    def _compute_end_date(self):
        for rec in self:
            if rec.start_date and rec.template_id and rec.template_id.duration_weeks:
                rec.end_date = rec.start_date + relativedelta(weeks=rec.template_id.duration_weeks)
            else:
                rec.end_date = False

    @api.depends("template_id.goal_type", "health_assessment_id.goal")
    def _compute_goal_mismatch(self):
        for rec in self:
            rec.goal_mismatch = bool(
                rec.template_id
                and rec.health_assessment_id
                and rec.template_id.goal_type != rec.health_assessment_id.goal,
            )

    @api.onchange("membership_id")
    def _onchange_membership_id(self):
        if self.membership_id:
            self.trainer_id = self.membership_id.trainer_id

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
                    "sequence": tl.sequence,
                    "day_of_week": tl.day_of_week,
                    "exercise_id": tl.exercise_id.id,
                    "equipment_id": tl.equipment_id.id,
                    "sets": tl.sets,
                    "reps": tl.reps,
                    "rest_seconds": tl.rest_seconds,
                    "notes": tl.notes,
                },
            )
            for tl in template.line_ids
        ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("gym.workout.plan") or "New"
            if vals.get("template_id") and not vals.get("line_ids"):
                template = self.env["gym.workout.template"].browse(vals["template_id"])
                vals["line_ids"] = self._lines_from_template(template)
        return super().create(vals_list)

    def unlink(self):
        for rec in self:
            if rec.state in ("active", "completed"):
                raise UserError(
                    _(
                        'Workout Plan "%s" cannot be deleted because it is %s. '
                        "Mark it Completed/keep it for history instead.",
                    )
                    % (rec.name, rec.state),
                )
        return super().unlink()

    def copy(self, default=None):
        raise UserError(_("Workout Plans cannot be duplicated. Create a new plan from a Health Assessment instead."))

    def action_activate(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Cannot activate a Workout Plan with no Exercise Lines."))
            rec.state = "active"

    def action_complete(self):
        self.state = "completed"

    def action_view_previous(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Previous Version"),
            "res_model": "gym.workout.plan",
            "view_mode": "form",
            "res_id": self.previous_plan_id.id,
        }


class GymWorkoutPlanLine(models.Model):
    _name = "gym.workout.plan.line"
    _description = "Workout Plan Line"
    _order = "sequence, day_of_week"
    _check_company_auto = True

    plan_id = fields.Many2one("gym.workout.plan", string="Plan", required=True, ondelete="cascade")
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="plan_id.company_id",
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
    exercise_id = fields.Many2one("gym.exercise", string="Exercise", required=True, check_company=True)
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
    rest_seconds = fields.Integer(string="Rest (sec)", default=60)
    notes = fields.Char(string="Notes", translate=True)
    completed = fields.Boolean(string="Completed", default=False)
    state = fields.Selection(related="plan_id.state", string="Plan Status")

    @api.onchange("exercise_id")
    def _onchange_exercise_id(self):
        if self.equipment_id and self.equipment_id not in self.exercise_id.equipment_ids:
            self.equipment_id = False
