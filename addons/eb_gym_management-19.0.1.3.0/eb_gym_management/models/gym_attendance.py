# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class GymAttendance(models.Model):
    _name = "gym.attendance"
    _description = "Member Attendance"
    _inherit = ["mail.thread"]
    _order = "check_in desc"
    _check_company_auto = True

    name = fields.Char(string="Reference", readonly=True, copy=False, default="New")
    partner_id = fields.Many2one(
        "res.partner",
        string="Member",
        required=True,
        tracking=True,
        domain=[("is_member", "=", True)],
        check_company=True,
    )
    membership_id = fields.Many2one(
        "gym.membership",
        string="Membership",
        required=True,
        tracking=True,
        domain=[("state", "=", "active")],
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="membership_id.company_id",
        store=True,
        index=True,
        readonly=True,
    )
    check_in = fields.Datetime(string="Check In", required=True, default=fields.Datetime.now)
    check_out = fields.Datetime(string="Check Out", tracking=True)
    duration = fields.Float(
        string="Duration (hrs)",
        compute="_compute_duration",
        store=True,
    )
    workout_plan_id = fields.Many2one(
        "gym.workout.plan",
        string="Workout Plan",
        domain="[('membership_id', '=', membership_id), ('state', '=', 'active')]",
    )

    @api.depends("check_in", "check_out")
    def _compute_duration(self):
        for rec in self:
            if rec.check_in and rec.check_out:
                delta = rec.check_out - rec.check_in
                rec.duration = delta.total_seconds() / 3600
            else:
                rec.duration = 0.0

    @api.constrains("membership_id")
    def _check_active_membership(self):
        for rec in self:
            if not rec.membership_id:
                continue
            if rec.membership_id.state == "on_hold":
                raise ValidationError(_("Membership is on hold — cannot check in."))
            if rec.membership_id.state != "active":
                raise ValidationError(_("Membership is not active — cannot check in."))

    @api.constrains("check_in", "check_out")
    def _check_checkout_after_checkin(self):
        for rec in self:
            if rec.check_out and rec.check_in and rec.check_out <= rec.check_in:
                raise ValidationError(_("Check Out time must be after Check In time."))

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        if self.partner_id:
            active_membership = self.env["gym.membership"].search(
                [
                    ("partner_id", "=", self.partner_id.id),
                    ("state", "=", "active"),
                ],
                limit=1,
            )
            self.membership_id = active_membership

    @api.onchange("membership_id")
    def _onchange_membership_id(self):
        self.workout_plan_id = self._get_member_workout_plan(self.membership_id)

    def _get_member_workout_plan(self, membership):
        """Best-guess workout plan for a membership: prefer an active plan,
        otherwise fall back to the most recently created plan (e.g. one
        generated from an assessment's chosen workout template but not yet
        activated)."""
        if not membership:
            return self.env["gym.workout.plan"].sudo()
        plan = (
            self.env["gym.workout.plan"]
            .sudo()
            .search(
                [
                    ("membership_id", "=", membership.id),
                    ("state", "=", "active"),
                ],
                limit=1,
            )
        )
        if plan:
            return plan
        return (
            self.env["gym.workout.plan"]
            .sudo()
            .search(
                [
                    ("membership_id", "=", membership.id),
                ],
                order="id desc",
                limit=1,
            )
        )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("gym.attendance") or "New"
            if not vals.get("workout_plan_id") and vals.get("membership_id"):
                membership = self.env["gym.membership"].browse(vals["membership_id"])
                plan = self._get_member_workout_plan(membership)
                if plan:
                    vals["workout_plan_id"] = plan.id
        return super().create(vals_list)

    def unlink(self):
        for rec in self:
            if rec.check_out:
                raise UserError(
                    _('Attendance record "%s" cannot be deleted because the member has already checked out.')
                    % rec.name,
                )
        return super().unlink()

    def copy(self, default=None):
        raise UserError(_("Attendance records cannot be duplicated."))

    def action_check_out(self):
        for rec in self:
            if rec.check_out:
                raise UserError(_("Member has already checked out."))
            rec.check_out = fields.Datetime.now()

    @api.model
    def _cron_checkout_reminder(self):
        """Daily cron — notify about members checked in for over 12 hours."""
        from datetime import timedelta

        threshold = fields.Datetime.now() - timedelta(hours=12)
        records = self.search(
            [
                ("check_out", "=", False),
                ("check_in", "<=", threshold),
            ],
        )
        for rec in records:
            rec.message_post(
                body=_("Alert: %s has been checked in since %s (over 12 hours). Please verify check-out.")
                % (rec.partner_id.name, rec.check_in.strftime("%d/%m/%Y %H:%M")),
                partner_ids=rec.membership_id.trainer_id.user_id.partner_id.ids if rec.membership_id.trainer_id else [],
            )
