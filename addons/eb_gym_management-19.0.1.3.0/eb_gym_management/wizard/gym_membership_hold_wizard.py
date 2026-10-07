# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class GymMembershipHoldWizard(models.TransientModel):
    _name = "gym.membership.hold.wizard"
    _description = "Membership Hold Wizard"

    membership_id = fields.Many2one(
        "gym.membership",
        string="Membership",
        required=True,
        readonly=True,
    )
    max_hold_days = fields.Integer(
        string="Configured Max Hold Days",
        related="membership_id.company_id.gym_max_hold_days",
        readonly=True,
    )
    remaining_hold_days = fields.Integer(
        string="Remaining Allowance",
        related="membership_id.hold_days_remaining",
        readonly=True,
    )
    hold_from_date = fields.Date(
        string="Hold From",
        required=True,
        readonly=False,
        default=fields.Date.today,
        help="First day of the hold period. Can be today or a future date.",
    )
    hold_to_date = fields.Date(
        string="Hold To",
        required=True,
        readonly=False,
        help="Last day of the hold period (inclusive).",
    )
    hold_days = fields.Integer(
        string="Hold Days",
        compute="_compute_hold_days",
        readonly=True,
        help="Auto-calculated inclusive days between Hold From and Hold To.",
    )
    hold_reason = fields.Text(string="Reason")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = fields.Date.today()
        res.setdefault("hold_from_date", today)
        res.setdefault("hold_to_date", today)
        membership_id = res.get("membership_id") or self.env.context.get("default_membership_id")
        if membership_id and "hold_reason" in fields_list:
            membership = self.env["gym.membership"].browse(membership_id)
            if membership.exists() and membership.hold_reason:
                res.setdefault("hold_reason", membership.hold_reason)
        return res

    @api.depends("hold_from_date", "hold_to_date")
    def _compute_hold_days(self):
        for rec in self:
            if rec.hold_from_date and rec.hold_to_date and rec.hold_to_date >= rec.hold_from_date:
                rec.hold_days = (rec.hold_to_date - rec.hold_from_date).days + 1
            else:
                rec.hold_days = 0

    @api.constrains("hold_from_date", "hold_to_date", "remaining_hold_days")
    def _check_hold_period(self):
        today = fields.Date.today()
        for rec in self:
            if not rec.hold_from_date or not rec.hold_to_date:
                raise ValidationError(_("Please select both Hold From and Hold To dates."))
            if rec.hold_from_date < today:
                raise ValidationError(_("Hold From date cannot be in the past."))
            if rec.hold_to_date < rec.hold_from_date:
                raise ValidationError(_("Hold To date must be on or after Hold From date."))
            if rec.hold_days <= 0:
                raise ValidationError(_("Hold Days must be greater than 0."))
            if rec.remaining_hold_days <= 0:
                raise ValidationError(_("No hold days are available for this membership."))
            if rec.hold_days > rec.remaining_hold_days:
                raise ValidationError(
                    _("Hold period is %s day(s), but only %s day(s) remain in the allowance.")
                    % (rec.hold_days, rec.remaining_hold_days),
                )

    def action_confirm_hold(self):
        self.ensure_one()
        self.membership_id.action_apply_hold(
            self.hold_from_date,
            self.hold_to_date,
            self.hold_reason,
        )
        return {"type": "ir.actions.act_window_close"}
