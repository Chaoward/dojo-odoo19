# -*- coding: utf-8 -*-
from collections import defaultdict

from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_date, format_datetime


class GymMembership(models.Model):
    _name = "gym.membership"
    _description = "Gym Membership"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    _rec_name = "name"
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
    plan_id = fields.Many2one(
        "product.template",
        string="Membership Plan",
        required=True,
        tracking=True,
        domain="[('is_gym_membership_plan', '=', True)]",
        check_company=True,
    )
    plan_includes_workout = fields.Boolean(
        string="Includes Workout Plan",
        related="plan_id.gym_includes_workout",
        readonly=True,
    )
    plan_includes_diet = fields.Boolean(
        string="Includes Diet Plan",
        related="plan_id.gym_includes_diet",
        readonly=True,
    )
    start_date = fields.Date(string="Start Date", default=fields.Date.today, tracking=True)
    end_date = fields.Date(string="End Date", compute="_compute_end_date", store=True, tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("on_hold", "On Hold"),
            ("expired", "Expired"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        tracking=True,
        copy=False,
    )
    hold_start_date = fields.Date(string="Hold Start Date", tracking=True, copy=False)
    hold_end_date = fields.Date(
        string="Hold End Date",
        tracking=True,
        copy=False,
        help="Last day of the current hold period (inclusive).",
    )
    hold_planned_days = fields.Integer(
        string="Current Hold Planned Days",
        default=0,
        copy=False,
        help="Planned days for the current hold period (already applied to allowance).",
    )
    hold_scheduled = fields.Boolean(
        string="Hold Scheduled",
        default=False,
        copy=False,
        help="True when a future hold period is booked but has not started yet.",
    )
    hold_reason = fields.Text(string="Hold Reason", tracking=True, copy=False)
    hold_days_used = fields.Integer(
        string="Hold Days Used",
        default=0,
        readonly=True,
        copy=False,
        help="Total days this membership has been paused.",
    )
    hold_extension_days = fields.Integer(
        string="Hold Extension Days",
        default=0,
        readonly=True,
        copy=False,
        help="Extra days added to the membership end date from hold periods.",
    )
    renewal_extension_days = fields.Integer(
        string="Renewal Extension Days",
        default=0,
        readonly=True,
        copy=False,
        help="Extra days added to the membership end date from paid renewals.",
    )
    pending_renewal_plan_id = fields.Many2one(
        "product.template",
        string="Pending Renewal Plan",
        copy=False,
        domain="[('is_gym_membership_plan', '=', True)]",
    )
    pending_renewal_end_date = fields.Date(
        string="Pending Renewal End Date",
        copy=False,
        help="New end date that will be applied after the renewal invoice is paid.",
    )
    company_gym_allow_hold = fields.Boolean(
        string="Hold Allowed (Company)",
        related="company_id.gym_allow_hold",
    )
    hold_days_remaining = fields.Integer(
        string="Hold Days Remaining",
        compute="_compute_hold_days_remaining",
    )
    sale_order_id = fields.Many2one(
        "sale.order",
        string="Sales Order",
        readonly=True,
        copy=False,
    )
    invoice_ids = fields.Many2many(
        "account.move",
        string="Invoices",
        compute="_compute_invoice_ids",
    )
    invoice_count = fields.Integer(string="Invoices", compute="_compute_invoice_ids")
    payment_state = fields.Selection(
        [
            ("not_paid", "Not Paid"),
            ("in_payment", "In Payment"),
            ("paid", "Paid"),
            ("partial", "Partially Paid"),
            ("reversed", "Reversed"),
        ],
        string="Payment Status",
        compute="_compute_payment_state",
        store=True,
    )
    trainer_id = fields.Many2one(
        "hr.employee",
        string="Assigned Trainer",
        tracking=True,
        domain=[("is_trainer", "=", True)],
        check_company=True,
    )
    renewal_count = fields.Integer(string="Renewals", default=0, copy=False)
    reminder_sent_date = fields.Date(string="Reminder Sent", copy=False)
    is_renewal_due = fields.Boolean(
        string="Renewal Due",
        compute="_compute_is_renewal_due",
        store=False,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )

    # Smart button backing fields
    health_assessment_ids = fields.One2many(
        "gym.health.assessment",
        "membership_id",
        string="Health Assessments",
    )
    workout_plan_ids = fields.One2many(
        "gym.workout.plan",
        "membership_id",
        string="Workout Plans",
    )
    diet_plan_ids = fields.One2many(
        "gym.diet.plan",
        "membership_id",
        string="Diet Plans",
    )
    attendance_ids = fields.One2many(
        "gym.attendance",
        "membership_id",
        string="Attendances",
    )
    health_assessment_count = fields.Integer(compute="_compute_counts")
    workout_plan_count = fields.Integer(compute="_compute_counts")
    diet_plan_count = fields.Integer(compute="_compute_counts")
    attendance_count = fields.Integer(compute="_compute_counts")

    def _compute_counts(self):
        for rec in self:
            rec.health_assessment_count = len(rec.health_assessment_ids.sudo())
            rec.workout_plan_count = len(rec.workout_plan_ids.sudo())
            rec.diet_plan_count = len(rec.diet_plan_ids.sudo())
            rec.attendance_count = len(rec.attendance_ids.sudo())

    @api.depends("company_id.gym_max_hold_days", "hold_days_used")
    def _compute_hold_days_remaining(self):
        for rec in self:
            max_days = rec.company_id.gym_max_hold_days or 0
            rec.hold_days_remaining = max(0, max_days - rec.hold_days_used)

    @api.depends("end_date", "state")
    def _compute_is_renewal_due(self):
        today = fields.Date.today()
        for rec in self:
            if rec.end_date and rec.state in ("active", "expired"):
                rec.is_renewal_due = rec.end_date <= today + relativedelta(days=1)
            else:
                rec.is_renewal_due = False

    @api.depends("sale_order_id")
    def _compute_invoice_ids(self):
        for rec in self:
            invoices = rec.sale_order_id.invoice_ids if rec.sale_order_id else self.env["account.move"]
            rec.invoice_ids = invoices
            rec.invoice_count = len(invoices)

    @api.depends("sale_order_id", "sale_order_id.invoice_ids.payment_state")
    def _compute_payment_state(self):
        for rec in self:
            invoices = (
                rec.sale_order_id.invoice_ids.filtered(
                    lambda inv: inv.move_type == "out_invoice" and inv.state == "posted",
                )
                if rec.sale_order_id
                else self.env["account.move"]
            )
            if not invoices:
                rec.payment_state = "not_paid"
            elif all(inv.payment_state == "paid" for inv in invoices):
                rec.payment_state = "paid"
            elif any(inv.payment_state == "in_payment" for inv in invoices):
                rec.payment_state = "in_payment"
            elif any(inv.payment_state == "partial" for inv in invoices):
                rec.payment_state = "partial"
            else:
                rec.payment_state = "not_paid"

    @api.depends(
        "start_date",
        "plan_id",
        "plan_id.gym_duration_value",
        "plan_id.gym_duration_uom",
        "hold_extension_days",
        "renewal_extension_days",
    )
    def _compute_end_date(self):
        for rec in self:
            if rec.start_date and rec.plan_id and rec.plan_id.gym_duration_value:
                uom = rec.plan_id.gym_duration_uom
                val = rec.plan_id.gym_duration_value
                if uom == "days":
                    base_end = rec.start_date + relativedelta(days=val)
                elif uom == "months":
                    base_end = rec.start_date + relativedelta(months=val)
                elif uom == "years":
                    base_end = rec.start_date + relativedelta(years=val)
                else:
                    base_end = False
                if base_end:
                    extra_days = (rec.hold_extension_days or 0) + (rec.renewal_extension_days or 0)
                    rec.end_date = base_end + relativedelta(days=extra_days)
                else:
                    rec.end_date = False
            else:
                rec.end_date = False

    def _plan_duration_end(self, from_date, plan):
        """Return from_date + plan duration."""
        self.ensure_one()
        if not from_date or not plan or not plan.gym_duration_value:
            return False
        uom = plan.gym_duration_uom
        val = plan.gym_duration_value
        if uom == "days":
            return from_date + relativedelta(days=val)
        if uom == "months":
            return from_date + relativedelta(months=val)
        if uom == "years":
            return from_date + relativedelta(years=val)
        return False

    def _compute_renewal_extension_for_end(self, plan, new_end):
        """Days to store in renewal_extension_days so computed end_date equals new_end."""
        self.ensure_one()
        if not self.start_date or not plan or not new_end:
            return 0
        base_end = self._plan_duration_end(self.start_date, plan)
        if not base_end:
            return 0
        base_end = base_end + relativedelta(days=self.hold_extension_days or 0)
        return (new_end - base_end).days

    @api.constrains("start_date", "end_date")
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.end_date <= rec.start_date:
                raise ValidationError(_("End date must be after start date."))

    @api.constrains("partner_id", "state")
    def _check_active_membership(self):
        for rec in self:
            if rec.state == "active":
                duplicate = self.search(
                    [
                        ("partner_id", "=", rec.partner_id.id),
                        ("state", "=", "active"),
                        ("id", "!=", rec.id),
                    ],
                )
                if duplicate:
                    raise ValidationError(_("Member %s already has an active membership.") % rec.partner_id.name)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("gym.membership") or "New"
        return super().create(vals_list)

    def unlink(self):
        for rec in self:
            if rec.state != "draft" or rec.sale_order_id:
                raise UserError(
                    _('Membership "%s" cannot be deleted because it has already been confirmed. ' "Cancel it instead.")
                    % rec.name,
                )
        return super().unlink()

    def copy(self, default=None):
        raise UserError(_('Memberships cannot be duplicated. Use "Renew" to extend an existing membership.'))

    def write(self, vals):
        was_active = {rec.id: rec.state == "active" for rec in self} if "state" in vals else {}
        res = super().write(vals)
        if "state" in vals:
            for rec in self:
                if rec.state == "active":
                    if not rec.partner_id.is_member:
                        rec.partner_id.is_member = True
                elif rec.state == "on_hold":
                    if not rec.partner_id.is_member:
                        rec.partner_id.is_member = True
                elif was_active.get(rec.id):
                    other_membership = self.search(
                        [
                            ("partner_id", "=", rec.partner_id.id),
                            ("state", "in", ("active", "on_hold")),
                            ("id", "!=", rec.id),
                        ],
                        limit=1,
                    )
                    if not other_membership:
                        rec.partner_id.is_member = False
        return res

    def _check_hold_allowed(self):
        self.ensure_one()
        if not self.company_id.gym_allow_hold:
            raise UserError(_("Membership hold/pause is not enabled. Enable it in Gym Configuration → Settings."))
        if self.hold_days_remaining <= 0:
            raise UserError(
                _("No hold days remaining for membership %s. Maximum allowance: %s days.")
                % (self.name, self.company_id.gym_max_hold_days),
            )

    def _get_open_attendance(self):
        self.ensure_one()
        return self.env["gym.attendance"].search(
            [
                ("membership_id", "=", self.id),
                ("check_out", "=", False),
            ],
            limit=1,
        )

    def action_hold_membership(self):
        self.ensure_one()
        if self.state != "active":
            raise UserError(_("Only active memberships can be put on hold."))
        if self.hold_scheduled:
            raise UserError(
                _("Membership %s already has a scheduled hold from %s to %s.")
                % (
                    self.name,
                    format_date(self.env, self.hold_start_date),
                    format_date(self.env, self.hold_end_date),
                ),
            )
        self._check_hold_allowed()
        if self._get_open_attendance():
            raise UserError(
                _("Member %s is currently checked in. Check them out before pausing the membership.")
                % self.partner_id.name,
            )
        today = fields.Date.today()
        return {
            "type": "ir.actions.act_window",
            "name": _("Pause Membership"),
            "res_model": "gym.membership.hold.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_membership_id": self.id,
                "default_hold_from_date": today,
                "default_hold_to_date": today,
                "default_hold_reason": self.hold_reason,
            },
        }

    def _get_hold_days_used_so_far(self, as_of_date=None):
        """Inclusive days used from hold_start_date up to as_of_date (capped by planned)."""
        self.ensure_one()
        if not self.hold_start_date or self.hold_scheduled:
            return 0
        as_of = as_of_date or fields.Date.today()
        if as_of < self.hold_start_date:
            return 0
        actual = (as_of - self.hold_start_date).days + 1
        planned = self.hold_planned_days or actual
        return min(actual, planned)

    def action_resume_membership(self):
        for rec in self:
            if rec.hold_scheduled and rec.state == "active":
                # Cancel a future scheduled hold before it starts.
                rec.write(
                    {
                        "hold_start_date": False,
                        "hold_end_date": False,
                        "hold_planned_days": 0,
                        "hold_scheduled": False,
                        "hold_reason": False,
                    },
                )
                rec.message_post(body=_("Scheduled hold was cancelled before it started."))
                continue

            if rec.state != "on_hold":
                raise UserError(_("Only memberships on hold can be resumed."))
            if not rec.hold_start_date:
                raise UserError(_("Hold start date is missing. Please contact an administrator."))

            today = fields.Date.today()
            planned = rec.hold_planned_days or 0
            used = rec._get_hold_days_used_so_far(today)
            unused = max(0, planned - used)

            vals = {
                "state": "active",
                "hold_start_date": False,
                "hold_end_date": False,
                "hold_planned_days": 0,
                "hold_scheduled": False,
                "hold_reason": False,
            }
            # Days were applied at pause time; refund unused days on early resume.
            if unused:
                vals["hold_days_used"] = max(0, rec.hold_days_used - unused)
                vals["hold_extension_days"] = max(0, rec.hold_extension_days - unused)

            rec.write(vals)
            rec.message_post(
                body=_(
                    "Membership resumed. Hold used: %s day(s)%s. New end date: %s.",
                )
                % (
                    used,
                    (_(" (%s day(s) unused refunded)") % unused) if unused else "",
                    format_date(self.env, rec.end_date),
                ),
            )

    def action_apply_hold(self, hold_from_date, hold_to_date, hold_reason=False):
        self.ensure_one()
        if self.state != "active":
            raise UserError(_("Only active memberships can be put on hold."))
        if self.hold_scheduled:
            raise UserError(_("This membership already has a scheduled hold."))
        self._check_hold_allowed()

        today = fields.Date.today()
        if not hold_from_date or not hold_to_date:
            raise UserError(_("Please select both Hold From and Hold To dates."))
        if hold_from_date < today:
            raise UserError(_("Hold From date cannot be in the past."))
        if hold_to_date < hold_from_date:
            raise UserError(_("Hold To date must be on or after Hold From date."))

        hold_days = (hold_to_date - hold_from_date).days + 1
        if hold_days <= 0:
            raise UserError(_("Hold days must be greater than 0."))
        if hold_days > self.hold_days_remaining:
            raise UserError(
                _("Hold period cannot exceed the remaining allowance of %s day(s).") % self.hold_days_remaining,
            )
        if self._get_open_attendance():
            raise UserError(
                _("Member %s is currently checked in. Check them out before pausing the membership.")
                % self.partner_id.name,
            )

        # Future hold: keep membership active until the from-date, then cron activates it.
        if hold_from_date > today:
            self.write(
                {
                    "hold_start_date": hold_from_date,
                    "hold_end_date": hold_to_date,
                    "hold_planned_days": hold_days,
                    "hold_scheduled": True,
                    "hold_reason": hold_reason or False,
                },
            )
            body = _("Hold scheduled from %s to %s (%s day(s)). Membership stays active until the hold starts.") % (
                format_date(self.env, hold_from_date),
                format_date(self.env, hold_to_date),
                hold_days,
            )
            if hold_reason:
                body += "<br/>%s" % (_("Reason: %s") % hold_reason)
            self.message_post(body=body)
            return

        self._activate_hold_period(hold_from_date, hold_to_date, hold_days, hold_reason)

    def _activate_hold_period(self, hold_from_date, hold_to_date, hold_days, hold_reason=False):
        """Move membership to on_hold and apply allowance/extension days."""
        self.ensure_one()
        self.write(
            {
                "state": "on_hold",
                "hold_start_date": hold_from_date,
                "hold_end_date": hold_to_date,
                "hold_planned_days": hold_days,
                "hold_scheduled": False,
                "hold_reason": hold_reason or False,
                "hold_days_used": self.hold_days_used + hold_days,
                "hold_extension_days": self.hold_extension_days + hold_days,
            },
        )
        body = _("Membership put on hold from %s to %s (%s day(s)).") % (
            format_date(self.env, hold_from_date),
            format_date(self.env, hold_to_date),
            hold_days,
        )
        if hold_reason:
            body += "<br/>%s" % (_("Reason: %s") % hold_reason)
        self.message_post(body=body)

    def action_confirm_membership(self):
        """Create Sales Order + Invoice with full membership details; redirect to invoice."""
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("Membership is not in Draft state."))
        if self.sale_order_id:
            raise UserError(
                _('Membership "%s" is already confirmed and linked to Sales Order %s.')
                % (self.name, self.sale_order_id.name),
            )
        if not self.plan_id:
            raise UserError(_("Please select a Membership Plan before confirming."))
        product_product = self.plan_id.product_variant_id
        if not product_product:
            raise UserError(_("The selected Membership Plan has no product variant."))

        # Build a descriptive line name
        duration_label = "%s %s" % (self.plan_id.gym_duration_value, self.plan_id.gym_duration_uom.capitalize())
        line_description = "%s — %s" % (self.plan_id.name, duration_label)
        if self.start_date and self.end_date:
            line_description += "\n%s: %s → %s" % (
                _("Period"),
                self.start_date.strftime("%d/%m/%Y"),
                self.end_date.strftime("%d/%m/%Y"),
            )

        # Build narration with all membership details
        narration_lines = [
            _("Membership Reference: %s") % self.name,
            _("Member: %s") % self.partner_id.name,
            _("Plan: %s") % self.plan_id.name,
            _("Duration: %s") % duration_label,
        ]
        if self.start_date:
            narration_lines.append(_("Start Date: %s") % self.start_date.strftime("%d/%m/%Y"))
        if self.end_date:
            narration_lines.append(_("End Date: %s") % self.end_date.strftime("%d/%m/%Y"))
        if self.trainer_id:
            narration_lines.append(_("Assigned Trainer: %s") % self.trainer_id.name)
        narration = "\n".join(narration_lines)

        # sudo(): confirming a membership is a well-defined, narrow business
        # action - not a general Sales/Accounting task - so gym staff (who
        # correctly don't hold Sales/Accounting app permissions) can trigger
        # it without being handed broad access to unrelated sale orders or
        # invoices. Read-only, gym-scoped visibility into the result is
        # granted separately (see rule_sale_order_gym_staff / _account_move).
        order = (
            self.env["sale.order"]
            .sudo()
            .create(
                {
                    "partner_id": self.partner_id.id,
                    "company_id": self.company_id.id,
                    "note": narration,
                    "order_line": [
                        (
                            0,
                            0,
                            {
                                "product_id": product_product.id,
                                "name": line_description,
                                "product_uom_qty": 1,
                                "price_unit": self.plan_id.list_price,
                            },
                        ),
                    ],
                },
            )
        )
        order.action_confirm()
        order._create_invoices()
        invoice = order.invoice_ids[:1]

        # Ensure narration also appears on the invoice
        if invoice:
            invoice.narration = narration

        self.sale_order_id = order
        self.message_post(body=_("Sales Order %s and Invoice %s created.") % (order.name, invoice.name or ""))

        return {
            "type": "ir.actions.act_window",
            "name": _("Invoice"),
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": invoice.id,
            "target": "current",
        }

    def action_set_active(self):
        """Activate membership — only allowed after invoice is paid."""
        for rec in self:
            if rec.payment_state not in ("paid", "in_payment"):
                raise UserError(_('Membership "%s" cannot be activated until the invoice is paid.') % rec.name)
            if rec.pending_renewal_end_date:
                rec._apply_pending_renewal()
                continue
            if not rec.start_date:
                rec.start_date = fields.Date.today()
            rec.state = "active"
            template = self.env.ref("eb_gym_management.mail_template_membership_welcome", raise_if_not_found=False)
            if template:
                template.send_mail(rec.id, force_send=True)
            rec.message_post(body=_("Membership activated after payment confirmation."))

    def _apply_pending_renewal(self):
        """Apply a paid renewal: extend end date via renewal_extension_days and activate."""
        for rec in self:
            if not rec.pending_renewal_end_date:
                continue
            plan = rec.pending_renewal_plan_id or rec.plan_id
            if not plan:
                raise UserError(_('Membership "%s" has a pending renewal but no plan to apply.') % rec.name)
            new_end = rec.pending_renewal_end_date
            extension_days = rec._compute_renewal_extension_for_end(plan, new_end)
            rec.write(
                {
                    "plan_id": plan.id,
                    "renewal_extension_days": extension_days,
                    "pending_renewal_plan_id": False,
                    "pending_renewal_end_date": False,
                    "renewal_count": rec.renewal_count + 1,
                    "state": "active",
                    "reminder_sent_date": False,
                },
            )
            template = self.env.ref("eb_gym_management.mail_template_membership_renewed", raise_if_not_found=False)
            if template:
                template.send_mail(rec.id, force_send=True)
            rec.message_post(
                body=_("Renewal applied after payment. New end date: %s.") % format_date(self.env, rec.end_date),
            )

    def _auto_activate_on_payment(self):
        """Called when linked invoice payment_state changes to paid/in_payment."""
        for rec in self:
            if rec.payment_state not in ("paid", "in_payment"):
                continue
            if rec.pending_renewal_end_date:
                rec._apply_pending_renewal()
            elif rec.state == "draft":
                if not rec.start_date:
                    rec.start_date = fields.Date.today()
                rec.state = "active"
                template = self.env.ref("eb_gym_management.mail_template_membership_welcome", raise_if_not_found=False)
                if template:
                    template.send_mail(rec.id, force_send=True)
                rec.message_post(body=_("Membership auto-activated upon payment."))

    def action_cancel(self):
        for rec in self:
            if rec.state in ("expired", "cancelled"):
                raise UserError(_("Cannot cancel a membership that is already expired or cancelled."))
            if rec.state == "on_hold" and rec._get_open_attendance():
                raise UserError(
                    _("Member %s is currently checked in. Check them out before cancelling.") % rec.partner_id.name,
                )
            vals = {
                "state": "cancelled",
                "hold_start_date": False,
                "hold_end_date": False,
                "hold_planned_days": 0,
                "hold_scheduled": False,
                "pending_renewal_plan_id": False,
                "pending_renewal_end_date": False,
            }
            # Refund unused hold days if cancelling during an active hold.
            if rec.state == "on_hold" and rec.hold_start_date and rec.hold_planned_days and not rec.hold_scheduled:
                used = rec._get_hold_days_used_so_far()
                unused = max(0, rec.hold_planned_days - used)
                if unused:
                    vals["hold_days_used"] = max(0, rec.hold_days_used - unused)
                    vals["hold_extension_days"] = max(0, rec.hold_extension_days - unused)
            rec.write(vals)
            rec.message_post(body=_("Membership cancelled."))

    def action_reset_draft(self):
        for rec in self:
            if rec.sale_order_id:
                raise UserError(
                    _(
                        'Membership "%s" cannot be reset to draft because it is linked to Sales Order %s. '
                        "Create a new membership instead.",
                    )
                    % (rec.name, rec.sale_order_id.name),
                )
            rec.write(
                {
                    "state": "draft",
                    "pending_renewal_plan_id": False,
                    "pending_renewal_end_date": False,
                },
            )

    def action_renew(self):
        self.ensure_one()
        if self.pending_renewal_end_date:
            raise UserError(
                _("A renewal is already pending payment for membership %s. Pay or cancel that invoice first.")
                % self.name,
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Renew Membership"),
            "res_model": "gym.membership.renew.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_membership_id": self.id},
        }

    @api.model
    def _cron_auto_expire(self):
        """Daily cron — expire active memberships whose end_date has passed."""
        today = fields.Date.today()
        expired = self.search(
            [
                ("state", "=", "active"),
                ("end_date", "<", today),
            ],
        )
        for rec in expired:
            rec.state = "expired"
            rec.message_post(body=_("Membership expired automatically on %s.") % today)
            template = self.env.ref("eb_gym_management.mail_template_membership_expired", raise_if_not_found=False)
            if template:
                template.send_mail(rec.id, force_send=False)

    @api.model
    def _cron_auto_resume_hold(self):
        """Daily cron — start scheduled holds and resume ended hold periods."""
        today = fields.Date.today()

        to_start = self.search(
            [
                ("state", "=", "active"),
                ("hold_scheduled", "=", True),
                ("hold_start_date", "!=", False),
                ("hold_start_date", "<=", today),
            ],
        )
        for rec in to_start:
            if rec._get_open_attendance():
                rec.message_post(
                    body=_(
                        "Scheduled hold could not start automatically because the member is still checked in.",
                    ),
                )
                continue
            rec._activate_hold_period(
                rec.hold_start_date,
                rec.hold_end_date,
                rec.hold_planned_days,
                rec.hold_reason,
            )

        to_resume = self.search(
            [
                ("state", "=", "on_hold"),
                ("hold_end_date", "!=", False),
                ("hold_end_date", "<", today),
            ],
        )
        for rec in to_resume:
            end_date = rec.hold_end_date
            rec.action_resume_membership()
            rec.message_post(
                body=_("Membership auto-resumed after hold period ended on %s.") % format_date(self.env, end_date),
            )

    @api.model
    def _cron_expiry_reminder(self):
        """Daily cron — send reminder for memberships expiring within 7 days."""
        today = fields.Date.today()
        from dateutil.relativedelta import relativedelta as rdelta

        remind_to = today + rdelta(days=7)
        records = self.search(
            [
                ("state", "=", "active"),
                ("end_date", ">=", today),
                ("end_date", "<=", remind_to),
                "|",
                ("reminder_sent_date", "=", False),
                ("reminder_sent_date", "<", today),
            ],
        )
        template = self.env.ref("eb_gym_management.mail_template_membership_expiry_reminder", raise_if_not_found=False)
        for rec in records:
            if template:
                template.send_mail(rec.id, force_send=False)
            rec.reminder_sent_date = today
            rec.message_post(body=_("Expiry reminder sent. Membership expires on %s.") % rec.end_date)

    # Smart button actions
    def action_view_invoices(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Invoices"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", self.invoice_ids.ids)],
        }

    def action_create_health_assessment(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("New Health Assessment"),
            "res_model": "gym.health.assessment",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_membership_id": self.id,
                "default_trainer_id": self.trainer_id.id,
            },
        }

    def action_view_health_assessments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Health Assessments"),
            "res_model": "gym.health.assessment",
            "view_mode": "list,form",
            "domain": [("membership_id", "=", self.id)],
            "context": {"default_membership_id": self.id},
        }

    def action_view_workout_plans(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Workout Plans"),
            "res_model": "gym.workout.plan",
            "view_mode": "list,form",
            "domain": [("membership_id", "=", self.id)],
            "context": {"default_membership_id": self.id},
        }

    def action_view_diet_plans(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Diet Plans"),
            "res_model": "gym.diet.plan",
            "view_mode": "list,form",
            "domain": [("membership_id", "=", self.id)],
            "context": {"default_membership_id": self.id},
        }

    def action_view_attendance(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Attendance"),
            "res_model": "gym.attendance",
            "view_mode": "list,form",
            "domain": [("membership_id", "=", self.id)],
        }

    # ==================== DASHBOARD ====================
    # Colors are pre-validated (CVD + normal-vision adjacency) against the
    # dataviz status palette — see the module's dashboard build notes.
    # Order matters: it is the sequence that passed the adjacency checks.
    _DASHBOARD_STATE_COLORS = {
        "active": "#0ca30c",
        "on_hold": "#4a3aa7",
        "draft": "#fab219",
        "cancelled": "#d03b3b",
        "expired": "#ec835a",
    }
    _DASHBOARD_PAYMENT_COLORS = {
        "paid": "#0ca30c",
        "in_payment": "#4a3aa7",
        "partial": "#fab219",
        "not_paid": "#d03b3b",
        "reversed": "#ec835a",
    }
    _DASHBOARD_ASSESSMENT_COLORS = {
        "draft": "#c3c2b7",
        "assigned": "#fab219",
        "in_progress": "#4a3aa7",
        "completed": "#0ca30c",
    }

    @api.model
    def _dashboard_range_config(self, date_range="6m"):
        today = fields.Date.today()
        months = {"3m": 3, "12m": 12}.get(date_range, 6)
        start_date = (today - relativedelta(months=months - 1)).replace(day=1)
        return {
            "key": date_range if date_range in ("3m", "6m", "12m") else "6m",
            "months": months,
            "start_date": start_date,
        }

    @api.model
    def _dashboard_month_series(self, model_name, date_field, domain, months):
        """Build a zero-filled monthly count series for the trailing `months` months."""
        today = fields.Date.today()
        series = {}
        for i in range(months - 1, -1, -1):
            month_date = (today - relativedelta(months=i)).replace(day=1)
            label = month_date.strftime("%b %Y")
            series[label] = {"name": label, "value": 0, "month_start": fields.Date.to_string(month_date)}

        Model = self.env[model_name]
        groups = Model._read_group(domain, ["%s:month" % date_field], ["__count"])
        for month_key, count in groups:
            if not month_key:
                continue
            label = fields.Date.to_date(month_key).strftime("%b %Y")
            if label in series:
                series[label]["value"] = count
        return list(series.values())

    @api.model
    def _dashboard_month_sum(self, model_name, date_field, sum_field, domain, months):
        today = fields.Date.today()
        series = {}
        for i in range(months - 1, -1, -1):
            month_date = (today - relativedelta(months=i)).replace(day=1)
            label = month_date.strftime("%b %Y")
            series[label] = {"name": label, "value": 0.0, "month_start": fields.Date.to_string(month_date)}

        Model = self.env[model_name]
        groups = Model._read_group(domain, ["%s:month" % date_field], [sum_field + ":sum"])
        for month_key, amount in groups:
            if not month_key:
                continue
            label = fields.Date.to_date(month_key).strftime("%b %Y")
            if label in series:
                series[label]["value"] = round(amount or 0.0, 2)
        return list(series.values())

    @api.model
    def get_dashboard_data(self, date_range="6m"):
        """Aggregate live gym data for the ECharts dashboard. Read-only, no side effects."""
        today = fields.Date.today()
        month_start = today.replace(day=1)
        week_ahead = today + relativedelta(days=7)
        range_config = self._dashboard_range_config(date_range)
        months = range_config["months"]

        Membership = self.sudo()
        Partner = self.env["res.partner"].sudo()
        Attendance = self.env["gym.attendance"].sudo()
        Employee = self.env["hr.employee"].sudo()
        AccountMove = self.env["account.move"].sudo()
        HealthAssessment = self.env["gym.health.assessment"].sudo()
        WorkoutPlan = self.env["gym.workout.plan"].sudo()
        DietPlan = self.env["gym.diet.plan"].sudo()
        StaffAttendance = self.env["hr.attendance"].sudo()

        # These KPI/aggregate queries run via sudo() (so a manager sees stats
        # across all trainers, not just their own "own records" scope) which
        # also bypasses branch record rules - so branch scoping has to be
        # applied explicitly here via the currently active companies.
        company_ids = self.env.companies.ids

        company_currency = self.env.company.currency_id
        gym_invoice_domain = [
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("invoice_line_ids.product_id.product_tmpl_id.is_gym_membership_plan", "=", True),
        ]

        # ---- KPIs ----
        total_members = Partner.search_count(
            [
                ("is_member", "=", True),
                ("membership_ids.company_id", "in", company_ids),
            ],
        )
        active_memberships = Membership.search_count(
            [
                ("state", "=", "active"),
                ("company_id", "in", company_ids),
            ],
        )
        new_members_this_month = Membership.search_count(
            [
                ("create_date", ">=", fields.Datetime.to_string(month_start)),
                ("company_id", "in", company_ids),
            ],
        )
        expiring_soon = Membership.search_count(
            [
                ("state", "=", "active"),
                ("end_date", "!=", False),
                ("end_date", ">=", today),
                ("end_date", "<=", week_ahead),
                ("company_id", "in", company_ids),
            ],
        )
        # Only memberships that have actually been invoiced (sale_order_id set,
        # via action_confirm_membership/renewal) count as "pending payment" -
        # a not-yet-confirmed draft also reads as payment_state=not_paid (no
        # invoices at all) but hasn't been billed, so it isn't "pending".
        pending_payments = Membership.search_count(
            [
                ("state", "=", "draft"),
                ("sale_order_id", "!=", False),
                ("payment_state", "in", ["not_paid", "partial"]),
                ("company_id", "in", company_ids),
            ],
        )
        revenue_this_month = sum(
            AccountMove.search(
                gym_invoice_domain + [("invoice_date", ">=", month_start), ("company_id", "in", company_ids)],
            ).mapped("amount_total"),
        )
        today_checkins = Attendance.search_count(
            [
                ("check_in", ">=", fields.Datetime.to_string(today)),
                ("check_in", "<", fields.Datetime.to_string(today + relativedelta(days=1))),
                ("company_id", "in", company_ids),
            ],
        )
        currently_in_gym = Attendance.search_count(
            [
                ("check_out", "=", False),
                ("company_id", "in", company_ids),
            ],
        )
        active_trainers = Employee.search_count(
            [
                ("is_trainer", "=", True),
                ("company_id", "in", company_ids),
            ],
        )

        recent_sessions = Attendance.search(
            [
                ("check_out", "!=", False),
                ("check_in", ">=", fields.Datetime.to_string(range_config["start_date"])),
                ("company_id", "in", company_ids),
            ],
        )
        avg_session_duration = (
            round(sum(recent_sessions.mapped("duration")) / len(recent_sessions), 1) if recent_sessions else 0.0
        )

        # ---- Membership status distribution (pie) ----
        state_counts = defaultdict(int)
        for state, count in Membership._read_group([("company_id", "in", company_ids)], ["state"], ["__count"]):
            if state:
                state_counts[state] = count
        state_labels = dict(self._fields["state"].selection)
        status_distribution = [
            {
                "state": state,
                "name": state_labels.get(state, state),
                "value": state_counts.get(state, 0),
                "color": color,
            }
            for state, color in self._DASHBOARD_STATE_COLORS.items()
        ]

        # ---- Payment status distribution (pie) ----
        payment_counts = defaultdict(int)
        for pay_state, count in Membership._read_group(
            [("state", "!=", "cancelled"), ("company_id", "in", company_ids)],
            ["payment_state"],
            ["__count"],
        ):
            if pay_state:
                payment_counts[pay_state] = count
        payment_labels = dict(self._fields["payment_state"].selection)
        payment_distribution = [
            {
                "state": pay_state,
                "name": payment_labels.get(pay_state, pay_state),
                "value": payment_counts.get(pay_state, 0),
                "color": color,
            }
            for pay_state, color in self._DASHBOARD_PAYMENT_COLORS.items()
            if payment_counts.get(pay_state, 0)
        ]

        # ---- Plan popularity (bar) ----
        plan_groups = Membership._read_group(
            [("plan_id", "!=", False), ("company_id", "in", company_ids)],
            ["plan_id"],
            ["__count"],
        )
        plan_popularity = sorted(
            ({"plan_id": plan.id, "name": plan.display_name, "value": count} for plan, count in plan_groups if plan),
            key=lambda item: item["value"],
            reverse=True,
        )[:8]

        # ---- Trends (all driven by the shared 3M/6M/12M range selector) ----
        monthly_new_members = self._dashboard_month_series(
            "gym.membership",
            "start_date",
            [("start_date", ">=", range_config["start_date"]), ("company_id", "in", company_ids)],
            months,
        )
        revenue_trend = self._dashboard_month_sum(
            "account.move",
            "invoice_date",
            "amount_total",
            gym_invoice_domain
            + [("invoice_date", ">=", range_config["start_date"]), ("company_id", "in", company_ids)],
            months,
        )

        # ---- Upcoming expirations table ----
        upcoming = Membership.search(
            [
                ("state", "=", "active"),
                ("end_date", "!=", False),
                ("end_date", ">=", today),
                ("company_id", "in", company_ids),
            ],
            order="end_date asc",
            limit=8,
        )
        upcoming_expirations = [
            {
                "id": m.id,
                "member": m.partner_id.display_name,
                "plan": m.plan_id.display_name,
                "end_date": format_date(self.env, m.end_date),
                "days_left": (m.end_date - today).days,
            }
            for m in upcoming
        ]

        # ---- Attendance trend (monthly, over the selected 3M/6M/12M range) ----
        attendance_trend = self._dashboard_month_series(
            "gym.attendance",
            "check_in",
            [
                ("check_in", ">=", fields.Datetime.to_string(range_config["start_date"])),
                ("company_id", "in", company_ids),
            ],
            months,
        )

        # ---- Peak hours (over the selected range) ----
        recent_checkins = Attendance.search(
            [
                ("check_in", ">=", fields.Datetime.to_string(range_config["start_date"])),
                ("company_id", "in", company_ids),
            ],
        )
        hour_counts = defaultdict(int)
        for att in recent_checkins:
            hour_counts[fields.Datetime.context_timestamp(att, att.check_in).hour] += 1
        hourly_attendance = [
            {"name": "%02d:00" % hour, "value": hour_counts.get(hour, 0), "hour": hour} for hour in range(24)
        ]

        # ---- Top trainers by active members (bar) ----
        trainer_groups = Membership._read_group(
            [("state", "=", "active"), ("trainer_id", "!=", False), ("company_id", "in", company_ids)],
            ["trainer_id"],
            ["__count"],
        )
        top_trainers = sorted(
            (
                {"trainer_id": trainer.id, "name": trainer.display_name, "value": count}
                for trainer, count in trainer_groups
                if trainer
            ),
            key=lambda item: item["value"],
            reverse=True,
        )[:8]

        # ---- Currently checked-in members (table) ----
        checked_in = Attendance.search(
            [("check_out", "=", False), ("company_id", "in", company_ids)],
            order="check_in asc",
            limit=10,
        )
        checked_in_now = [
            {
                "id": att.id,
                "member": att.partner_id.display_name,
                "trainer": att.membership_id.trainer_id.display_name or "",
                "check_in": format_datetime(self.env, att.check_in, dt_format="short"),
            }
            for att in checked_in
        ]

        # ==================== MEMBER CARE PIPELINE ====================
        # Health assessment funnel (pie/bar)
        assessment_state_counts = defaultdict(int)
        for state, count in HealthAssessment._read_group([("company_id", "in", company_ids)], ["state"], ["__count"]):
            if state:
                assessment_state_counts[state] = count
        assessment_labels = dict(HealthAssessment._fields["state"].selection)
        assessment_pipeline = [
            {
                "state": state,
                "name": assessment_labels.get(state, state),
                "value": assessment_state_counts.get(state, 0),
                "color": color,
            }
            for state, color in self._DASHBOARD_ASSESSMENT_COLORS.items()
        ]
        pending_assessments = assessment_state_counts.get("draft", 0) + assessment_state_counts.get("assigned", 0)
        active_workout_plans = WorkoutPlan.search_count(
            [
                ("state", "=", "active"),
                ("company_id", "in", company_ids),
            ],
        )
        active_diet_plans = DietPlan.search_count(
            [
                ("state", "=", "active"),
                ("company_id", "in", company_ids),
            ],
        )

        # Active members whose plan includes workout/diet coaching but who
        # have no active plan of that kind yet — an actionable service gap.
        members_needing_plan = Membership.search(
            [
                ("state", "=", "active"),
                ("company_id", "in", company_ids),
                "|",
                ("plan_includes_workout", "=", True),
                ("plan_includes_diet", "=", True),
            ],
        )
        awaiting_plan_rows = []
        for m in members_needing_plan:
            missing = []
            if m.plan_includes_workout and not m.workout_plan_ids.filtered(lambda p: p.state == "active"):
                missing.append(_("Workout"))
            if m.plan_includes_diet and not m.diet_plan_ids.filtered(lambda p: p.state == "active"):
                missing.append(_("Diet"))
            if missing:
                awaiting_plan_rows.append(
                    {
                        "id": m.id,
                        "member": m.partner_id.display_name,
                        "plan": m.plan_id.display_name,
                        "missing": " & ".join(str(x) for x in missing),
                        "since": format_date(self.env, m.start_date) if m.start_date else "",
                    },
                )
        members_awaiting_plan_count = len(awaiting_plan_rows)
        members_awaiting_plan = awaiting_plan_rows[:8]

        # ==================== STAFF ATTENDANCE & WORKLOAD ====================
        active_nutritionists = Employee.search_count(
            [
                ("is_nutritionist", "=", True),
                ("company_id", "in", company_ids),
            ],
        )
        staff_on_duty_now = StaffAttendance.search_count(
            [
                ("check_out", "=", False),
                ("employee_id.company_id", "in", company_ids),
            ],
        )
        staff_checkins_today = StaffAttendance.search_count(
            [
                ("check_in", ">=", fields.Datetime.to_string(today)),
                ("check_in", "<", fields.Datetime.to_string(today + relativedelta(days=1))),
                ("employee_id.company_id", "in", company_ids),
            ],
        )
        recent_staff_sessions = StaffAttendance.search(
            [
                ("check_out", "!=", False),
                ("check_in", ">=", fields.Datetime.to_string(range_config["start_date"])),
                ("employee_id.company_id", "in", company_ids),
            ],
        )
        avg_staff_session_duration = (
            round(sum(recent_staff_sessions.mapped("worked_hours")) / len(recent_staff_sessions), 1)
            if recent_staff_sessions
            else 0.0
        )

        # Staff attendance trend (monthly, over the selected 3M/6M/12M range)
        staff_attendance_trend = self._dashboard_month_series(
            "hr.attendance",
            "check_in",
            [
                ("check_in", ">=", fields.Datetime.to_string(range_config["start_date"])),
                ("employee_id.company_id", "in", company_ids),
            ],
            months,
        )

        # Staff currently on duty (table)
        def _staff_role_label(employee):
            roles = [
                label
                for cond, label in (
                    (employee.is_trainer, _("Trainer")),
                    (employee.is_nutritionist, _("Nutritionist")),
                    (employee.is_receptionist, _("Receptionist")),
                )
                if cond
            ]
            return " / ".join(roles) or _("Staff")

        on_duty = StaffAttendance.search(
            [("check_out", "=", False), ("employee_id.company_id", "in", company_ids)],
            order="check_in asc",
            limit=10,
        )
        on_duty_staff = [
            {
                "id": att.id,
                "employee": att.employee_id.display_name,
                "role": _staff_role_label(att.employee_id),
                "check_in": format_datetime(self.env, att.check_in, dt_format="short"),
            }
            for att in on_duty
        ]

        return {
            "dashboard_range_key": range_config["key"],
            "currency_symbol": company_currency.symbol,
            "currency_position": company_currency.position,
            "total_members": total_members,
            "active_memberships": active_memberships,
            "new_members_this_month": new_members_this_month,
            "expiring_soon": expiring_soon,
            "pending_payments": pending_payments,
            "revenue_this_month": round(revenue_this_month, 2),
            "today_checkins": today_checkins,
            "currently_in_gym": currently_in_gym,
            "active_trainers": active_trainers,
            "avg_session_duration": avg_session_duration,
            "status_distribution": status_distribution,
            "payment_distribution": payment_distribution,
            "plan_popularity": plan_popularity,
            "monthly_new_members": monthly_new_members,
            "revenue_trend": revenue_trend,
            "upcoming_expirations": upcoming_expirations,
            "attendance_trend": attendance_trend,
            "hourly_attendance": hourly_attendance,
            "top_trainers": top_trainers,
            "checked_in_now": checked_in_now,
            "assessment_pipeline": assessment_pipeline,
            "pending_assessments": pending_assessments,
            "active_workout_plans": active_workout_plans,
            "active_diet_plans": active_diet_plans,
            "members_awaiting_plan": members_awaiting_plan,
            "members_awaiting_plan_count": members_awaiting_plan_count,
            "active_nutritionists": active_nutritionists,
            "staff_on_duty_now": staff_on_duty_now,
            "staff_checkins_today": staff_checkins_today,
            "avg_staff_session_duration": avg_staff_session_duration,
            "staff_attendance_trend": staff_attendance_trend,
            "on_duty_staff": on_duty_staff,
        }
