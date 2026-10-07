# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class GymMembershipPlan(models.Model):
    """Extend product.template to carry gym membership plan data."""

    _inherit = "product.template"

    is_gym_membership_plan = fields.Boolean(
        string="Is Membership Plan",
        default=False,
        help="Enable to use this product as a Gym Membership Plan.",
    )
    gym_duration_value = fields.Integer(
        string="Duration",
        default=1,
        tracking=True,
    )
    gym_duration_uom = fields.Selection(
        [
            ("days", "Days"),
            ("months", "Months"),
            ("years", "Years"),
        ],
        string="Duration Unit",
        default="months",
        tracking=True,
    )
    gym_plan_code = fields.Char(string="Plan Code", translate=True)
    gym_includes_workout = fields.Boolean(
        string="Includes Workout Plan",
        default=False,
        help="Enable if members on this plan get a workout plan.",
    )
    gym_includes_diet = fields.Boolean(
        string="Includes Diet Plan",
        default=False,
        help="Enable if members on this plan get a diet plan.",
    )
    gym_benefits = fields.Html(string="Benefits", translate=True)
    gym_membership_count = fields.Integer(
        string="Memberships",
        compute="_compute_gym_membership_count",
    )

    @api.constrains("gym_duration_value", "is_gym_membership_plan")
    def _check_gym_duration(self):
        for rec in self:
            if rec.is_gym_membership_plan and rec.gym_duration_value <= 0:
                raise ValidationError(_("Duration must be greater than 0."))

    def _compute_gym_membership_count(self):
        MembershipPlan = self.env["gym.membership"]
        for rec in self:
            rec.gym_membership_count = MembershipPlan.search_count([("plan_id", "=", rec.id)])

    def action_view_gym_memberships(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Memberships"),
            "res_model": "gym.membership",
            "view_mode": "list,form",
            "domain": [("plan_id", "=", self.id)],
            "context": {"default_plan_id": self.id},
        }
