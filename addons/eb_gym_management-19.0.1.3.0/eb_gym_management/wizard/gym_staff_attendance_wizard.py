# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class GymStaffAttendanceWizard(models.TransientModel):
    _name = "gym.staff.attendance.wizard"
    _description = "Staff Attendance Check In / Check Out Wizard"

    employee_name = fields.Char(string="Employee", readonly=True, compute="_compute_summary")
    current_attendance_id = fields.Many2one(
        "hr.attendance",
        string="Open Attendance",
        readonly=True,
        compute="_compute_summary",
    )
    check_in = fields.Datetime(string="Check In", readonly=True, compute="_compute_summary")
    check_out = fields.Datetime(string="Check Out", readonly=True, compute="_compute_summary")
    state = fields.Selection(
        [("not_checked_in", "Not Checked In"), ("checked_in", "Checked In")],
        string="Status",
        readonly=True,
        compute="_compute_summary",
    )
    status_message = fields.Char(string="Message", readonly=True, compute="_compute_summary")

    @api.model
    def _get_current_employee(self):
        return self.env["hr.employee"].search([("user_id", "=", self.env.user.id)], limit=1)

    @api.depends_context("uid")
    def _compute_summary(self):
        for rec in self:
            employee = rec._get_current_employee()
            rec.employee_name = employee.name if employee else False
            checked_in = bool(employee) and employee.attendance_state == "checked_in"
            rec.current_attendance_id = employee.last_attendance_id if checked_in else False
            if not employee:
                rec.check_in = False
                rec.check_out = False
                rec.state = "not_checked_in"
                rec.status_message = _("No employee is linked to your user account.")
            elif checked_in:
                rec.check_in = rec.current_attendance_id.check_in
                rec.check_out = rec.current_attendance_id.check_out
                rec.state = "checked_in"
                rec.status_message = _("You are currently checked in.")
            else:
                rec.check_in = False
                rec.check_out = False
                rec.state = "not_checked_in"
                rec.status_message = _("You are not checked in right now.")

    def action_check_in(self):
        self.ensure_one()
        employee = self._get_current_employee()
        if not employee:
            raise UserError(_("No employee is linked to your user account. Please contact your administrator."))
        if employee.attendance_state == "checked_in":
            raise UserError(_("You are already checked in. Please check out first."))

        # Standard hr_attendance toggle - creates the hr.attendance record.
        employee._attendance_action_change()
        return {"type": "ir.actions.act_window_close"}

    def action_check_out(self):
        self.ensure_one()
        employee = self._get_current_employee()
        if not employee:
            raise UserError(_("No employee is linked to your user account. Please contact your administrator."))
        if employee.attendance_state != "checked_in":
            raise UserError(_("There is no open attendance to check out."))

        # Standard hr_attendance toggle - writes check_out on the open record.
        employee._attendance_action_change()
        return {"type": "ir.actions.act_window_close"}
