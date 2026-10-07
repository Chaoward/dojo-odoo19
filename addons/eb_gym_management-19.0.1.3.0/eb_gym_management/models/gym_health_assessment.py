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

# Fields the trainer fills in while working the assessment — writing any of
# these while 'assigned' auto-advances the record to 'in_progress'.
PROGRESS_FIELDS = {
    "height_cm",
    "weight_kg",
    "body_fat_pct",
    "waist_cm",
    "chest_cm",
    "medical_conditions",
    "injuries",
    "medication",
    "medical_restrictions",
    "fitness_level",
    "strength_level",
    "cardio_level",
    "flexibility",
    "workout_template_id",
    "diet_template_id",
    "next_assessment_date",
    "notes",
}


class GymHealthAssessment(models.Model):
    _name = "gym.health.assessment"
    _description = "Health Assessment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc"
    _check_company_auto = True

    name = fields.Char(string="Reference", readonly=True, copy=False, default="New")
    membership_id = fields.Many2one(
        "gym.membership",
        string="Membership",
        required=True,
        tracking=True,
        domain=[("state", "in", ["draft", "active"])],
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="membership_id.company_id",
        store=True,
        index=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Member",
        related="membership_id.partner_id",
        store=True,
    )
    plan_includes_workout = fields.Boolean(
        related="membership_id.plan_includes_workout",
        string="Includes Workout Plan",
    )
    plan_includes_diet = fields.Boolean(
        related="membership_id.plan_includes_diet",
        string="Includes Diet Plan",
    )
    trainer_id = fields.Many2one(
        "hr.employee",
        string="Trainer",
        tracking=True,
        domain=[("is_trainer", "=", True)],
        check_company=True,
    )
    nutritionist_id = fields.Many2one(
        "hr.employee",
        string="Nutritionist",
        tracking=True,
        domain=[("is_nutritionist", "=", True)],
        check_company=True,
    )
    date = fields.Date(string="Assessment Date", required=True, default=fields.Date.today)
    height_cm = fields.Float(string="Height (cm)")
    weight_kg = fields.Float(string="Weight (kg)")
    bmi = fields.Float(string="BMI", compute="_compute_bmi", store=True)
    body_fat_pct = fields.Float(string="Body Fat %")
    waist_cm = fields.Float(string="Waist (cm)")
    chest_cm = fields.Float(string="Chest (cm)")
    medical_conditions = fields.Text(string="Medical Conditions / Notes", translate=True)
    injuries = fields.Text(string="Injuries", translate=True)
    medication = fields.Text(string="Medication", translate=True)
    medical_restrictions = fields.Text(string="Medical Restrictions", translate=True)
    goal = fields.Selection(GOAL_TYPE_SELECTION, string="Fitness Goal", required=True, tracking=True)
    is_baseline = fields.Boolean(
        string="Baseline Assessment",
        compute="_compute_is_baseline",
        store=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("assigned", "Assigned"),
            ("in_progress", "In Progress"),
            ("completed", "Completed"),
        ],
        string="Status",
        default="draft",
        tracking=True,
    )

    fitness_level = fields.Char(string="Fitness Level", translate=True)
    strength_level = fields.Char(string="Strength Level", translate=True)
    cardio_level = fields.Char(string="Cardio Level", translate=True)
    flexibility = fields.Char(string="Flexibility", translate=True)

    workout_template_id = fields.Many2one(
        "gym.workout.template",
        string="Workout Template",
        domain="[('goal_type', '=', goal)] if goal else []",
    )
    diet_template_id = fields.Many2one(
        "gym.diet.template",
        string="Diet Template",
        domain="[('goal_type', '=', goal)] if goal else []",
    )
    next_assessment_date = fields.Date(string="Next Assessment Date")
    notes = fields.Text(string="Notes", translate=True)

    workout_plan_count = fields.Integer(compute="_compute_plan_counts")
    diet_plan_count = fields.Integer(compute="_compute_plan_counts")

    def _compute_plan_counts(self):
        for rec in self:
            rec.workout_plan_count = (
                self.env["gym.workout.plan"].sudo().search_count([("health_assessment_id", "=", rec.id)])
            )
            rec.diet_plan_count = self.env["gym.diet.plan"].sudo().search_count([("health_assessment_id", "=", rec.id)])

    @api.depends("weight_kg", "height_cm")
    def _compute_bmi(self):
        for rec in self:
            if rec.height_cm and rec.weight_kg:
                height_m = rec.height_cm / 100
                rec.bmi = round(rec.weight_kg / (height_m**2), 2)
            else:
                rec.bmi = 0.0

    @api.depends("membership_id")
    def _compute_is_baseline(self):
        for rec in self:
            if rec.membership_id:
                first = self.search(
                    [("membership_id", "=", rec.membership_id.id)],
                    order="date asc, id asc",
                    limit=1,
                )
                rec.is_baseline = first.id == rec.id
            else:
                rec.is_baseline = False

    @api.constrains("height_cm")
    def _check_height(self):
        for rec in self:
            if rec.height_cm and rec.height_cm < 0:
                raise ValidationError(_("Height cannot be negative."))

    @api.constrains("weight_kg")
    def _check_weight(self):
        for rec in self:
            if rec.weight_kg and rec.weight_kg < 0:
                raise ValidationError(_("Weight cannot be negative."))

    @api.constrains("body_fat_pct")
    def _check_body_fat(self):
        for rec in self:
            if rec.body_fat_pct and not (0 <= rec.body_fat_pct <= 100):
                raise ValidationError(_("Body Fat % must be between 0 and 100."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("gym.health.assessment") or "New"
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if "state" not in vals and PROGRESS_FIELDS & set(vals):
            assigned = self.filtered(lambda rec: rec.state == "assigned")
            if assigned:
                assigned.write({"state": "in_progress"})
        return res

    def unlink(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(
                    _(
                        'Health Assessment "%s" cannot be deleted because it is no longer in Draft state. '
                        "Reset it to Draft first if you are sure you want to remove it.",
                    )
                    % rec.name,
                )
        return super().unlink()

    def copy(self, default=None):
        raise UserError(_("Health Assessments cannot be duplicated. Create a new assessment instead."))

    def action_assign_notify(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only draft assessments can be assigned."))
            if not rec.goal:
                raise UserError(_("Please select a Fitness Goal before assigning."))
            if rec.plan_includes_workout and not rec.trainer_id:
                raise UserError(_("Please select a Trainer before assigning."))
            if rec.plan_includes_diet and not rec.nutritionist_id:
                raise UserError(_("Please select a Nutritionist before assigning."))
            if not rec.trainer_id and not rec.nutritionist_id:
                raise UserError(_("Please select a Trainer or Nutritionist before assigning."))

            staff = [
                (rec.trainer_id, _("Trainer")),
                (rec.nutritionist_id, _("Nutritionist")),
            ]
            for employee, role in staff:
                if employee and not employee.user_id:
                    raise UserError(
                        _('%s "%s" has no linked user account, so they cannot be notified.') % (role, employee.name),
                    )

            rec.state = "assigned"
            notify_partners = self.env["res.partner"]
            for employee, role in staff:
                if not employee:
                    continue
                rec.activity_schedule(
                    "mail.mail_activity_data_todo",
                    summary=_("Health Assessment Assigned: %s") % rec.name,
                    note=_(
                        "You have been assigned as %s to complete the health assessment for %s. "
                        "Please fill in the body measurements, health screening, fitness "
                        "evaluation and recommendations.",
                    )
                    % (role, rec.partner_id.name),
                    user_id=employee.user_id.id,
                )
                notify_partners |= employee.user_id.partner_id
            rec.message_post(
                body=_(
                    "Assessment assigned. Please open this record to fill in the body "
                    "measurements, health screening, fitness evaluation and recommendations.",
                ),
                partner_ids=notify_partners.ids,
            )

    def action_complete(self):
        for rec in self:
            if rec.state != "in_progress":
                raise UserError(_("Only assessments in progress can be completed."))
            if not rec.height_cm or not rec.weight_kg or not rec.goal:
                raise ValidationError(_("Height, Weight and Fitness Goal are required to complete."))
            rec.state = "completed"
            assigned_users = rec.trainer_id.user_id | rec.nutritionist_id.user_id
            rec.activity_ids.filtered(lambda a: a.user_id in assigned_users).action_feedback(
                feedback=_("Health assessment completed."),
            )
            rec.message_post(
                body=_("Assessment completed. Goal: %s | BMI: %.2f | Weight: %.1f kg")
                % (dict(rec._fields["goal"].selection).get(rec.goal), rec.bmi, rec.weight_kg),
            )
            template = self.env.ref(
                "eb_gym_management.mail_template_health_assessment_confirmed",
                raise_if_not_found=False,
            )
            if template:
                template.send_mail(rec.id, force_send=False)

    def action_reset_draft(self):
        self.state = "draft"

    def action_create_workout_plan(self):
        self.ensure_one()
        if not self.workout_template_id:
            raise UserError(_("Please select a Workout Template before creating a Workout Plan."))
        if not self.trainer_id:
            raise UserError(_("Please select a Trainer before creating a Workout Plan."))
        plan = self.env["gym.workout.plan"].create(
            {
                "membership_id": self.membership_id.id,
                "health_assessment_id": self.id,
                "template_id": self.workout_template_id.id,
                "trainer_id": self.trainer_id.id,
            },
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Workout Plan"),
            "res_model": "gym.workout.plan",
            "view_mode": "form",
            "res_id": plan.id,
            "target": "current",
        }

    def action_create_diet_plan(self):
        self.ensure_one()
        if not self.diet_template_id:
            raise UserError(_("Please select a Diet Template before creating a Diet Plan."))
        if not self.nutritionist_id:
            raise UserError(_("Please select a Nutritionist before creating a Diet Plan."))
        plan = self.env["gym.diet.plan"].create(
            {
                "membership_id": self.membership_id.id,
                "health_assessment_id": self.id,
                "template_id": self.diet_template_id.id,
                "nutritionist_id": self.nutritionist_id.id,
            },
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Diet Plan"),
            "res_model": "gym.diet.plan",
            "view_mode": "form",
            "res_id": plan.id,
            "target": "current",
        }

    def action_view_workout_plans(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Workout Plans"),
            "res_model": "gym.workout.plan",
            "view_mode": "list,form",
            "domain": [("health_assessment_id", "=", self.id)],
            "context": {
                "default_health_assessment_id": self.id,
                "default_membership_id": self.membership_id.id,
                "default_template_id": self.workout_template_id.id,
                "default_trainer_id": self.trainer_id.id,
            },
        }

    def action_view_diet_plans(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Diet Plans"),
            "res_model": "gym.diet.plan",
            "view_mode": "list,form",
            "domain": [("health_assessment_id", "=", self.id)],
            "context": {
                "default_health_assessment_id": self.id,
                "default_membership_id": self.membership_id.id,
                "default_template_id": self.diet_template_id.id,
                "default_nutritionist_id": self.nutritionist_id.id,
            },
        }
