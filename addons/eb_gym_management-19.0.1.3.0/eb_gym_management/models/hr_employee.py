# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# Employee boolean field -> security group XML ID it reflects.
GYM_ROLE_GROUP_XMLIDS = {
    "is_receptionist": "eb_gym_management.group_gym_reception",
    "is_trainer": "eb_gym_management.group_gym_trainer",
    "is_nutritionist": "eb_gym_management.group_gym_nutritionist",
    "is_branch_manager": "eb_gym_management.group_gym_branch_manager",
}


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # Read-only mirror of the linked user's Gym Receptionist / Trainer /
    # Nutritionist / Branch Manager access groups. These are granted from the
    # User's Access Rights tab (Settings > Users), not from this form; being a
    # plain stored compute depending on the group relation, this needs no custom
    # write/sync code to stay correct - it just recomputes automatically.
    is_receptionist = fields.Boolean(
        string="Is Receptionist",
        compute="_compute_gym_roles",
        store=True,
        readonly=True,
    )
    is_trainer = fields.Boolean(
        string="Is Trainer",
        compute="_compute_gym_roles",
        store=True,
        readonly=True,
    )
    is_nutritionist = fields.Boolean(
        string="Is Nutritionist",
        compute="_compute_gym_roles",
        store=True,
        readonly=True,
    )
    is_branch_manager = fields.Boolean(
        string="Is Branch Manager",
        compute="_compute_gym_roles",
        store=True,
        readonly=True,
    )
    specialization_ids = fields.Many2many(
        "gym.trainer.specialization",
        string="Specializations",
    )

    membership_count = fields.Integer(compute="_compute_gym_counts")
    health_assessment_count = fields.Integer(compute="_compute_gym_counts")
    workout_plan_count = fields.Integer(compute="_compute_gym_counts")
    diet_plan_count = fields.Integer(compute="_compute_gym_counts")
    staff_attendance_count = fields.Integer(compute="_compute_gym_counts")

    def _compute_gym_counts(self):
        membership_data = dict(
            self.env["gym.membership"]
            .sudo()
            ._read_group(
                [("trainer_id", "in", self.ids)],
                ["trainer_id"],
                ["__count"],
            ),
        )
        workout_plan_data = dict(
            self.env["gym.workout.plan"]
            .sudo()
            ._read_group(
                [("trainer_id", "in", self.ids)],
                ["trainer_id"],
                ["__count"],
            ),
        )
        diet_plan_data = dict(
            self.env["gym.diet.plan"]
            .sudo()
            ._read_group(
                [("nutritionist_id", "in", self.ids)],
                ["nutritionist_id"],
                ["__count"],
            ),
        )
        staff_attendance_data = dict(
            self.env["hr.attendance"]
            .sudo()
            ._read_group(
                [("employee_id", "in", self.ids)],
                ["employee_id"],
                ["__count"],
            ),
        )
        for rec in self:
            rec.membership_count = membership_data.get(rec, 0)
            rec.workout_plan_count = workout_plan_data.get(rec, 0)
            rec.diet_plan_count = diet_plan_data.get(rec, 0)
            rec.staff_attendance_count = staff_attendance_data.get(rec, 0)
            rec.health_assessment_count = (
                self.env["gym.health.assessment"]
                .sudo()
                .search_count(
                    [
                        "|",
                        ("trainer_id", "=", rec.id),
                        ("nutritionist_id", "=", rec.id),
                    ],
                )
            )

    def action_view_memberships(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Memberships"),
            "res_model": "gym.membership",
            "view_mode": "list,form",
            "domain": [("trainer_id", "=", self.id)],
        }

    def action_view_health_assessments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Health Assessments"),
            "res_model": "gym.health.assessment",
            "view_mode": "list,form",
            "domain": ["|", ("trainer_id", "=", self.id), ("nutritionist_id", "=", self.id)],
        }

    def action_view_workout_plans(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Workout Plans"),
            "res_model": "gym.workout.plan",
            "view_mode": "list,form",
            "domain": [("trainer_id", "=", self.id)],
        }

    def action_view_diet_plans(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Diet Plans"),
            "res_model": "gym.diet.plan",
            "view_mode": "list,form",
            "domain": [("nutritionist_id", "=", self.id)],
        }

    def action_view_staff_attendances(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Attendances"),
            "res_model": "hr.attendance",
            "view_mode": "list,form",
            "domain": [("employee_id", "=", self.id)],
            "context": {"default_employee_id": self.id},
        }

    @api.depends("user_id.all_group_ids")
    def _compute_gym_roles(self):
        role_groups = self._get_gym_role_groups()
        for employee in self:
            for field_name, group in role_groups.items():
                employee[field_name] = bool(group) and group in employee.user_id.all_group_ids
            for field_name in GYM_ROLE_GROUP_XMLIDS.keys() - role_groups.keys():
                employee[field_name] = False

    @api.model
    def _get_gym_role_groups(self):
        """Resolve GYM_ROLE_GROUP_XMLIDS to {field_name: res.groups record},
        logging (and skipping) any XML ID that can't be found instead of
        raising, so a broken/uninstalled reference never blocks HR writes.
        """
        role_groups = {}
        for field_name, xmlid in GYM_ROLE_GROUP_XMLIDS.items():
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if not group:
                _logger.warning(
                    "Gym role sync: security group '%s' not found, " "'%s' will always read as False.",
                    xmlid,
                    field_name,
                )
                continue
            role_groups[field_name] = group
        return role_groups
