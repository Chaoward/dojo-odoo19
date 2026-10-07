# -*- coding: utf-8 -*-
from odoo import Command, _, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_member = fields.Boolean(string="Is Member", default=False, tracking=True)
    membership_ids = fields.One2many(
        "gym.membership",
        "partner_id",
        string="Memberships",
    )
    membership_count = fields.Integer(
        string="Memberships",
        compute="_compute_membership_count",
    )
    has_portal_user = fields.Boolean(
        string="Has Portal User",
        compute="_compute_has_portal_user",
    )
    attendance_count = fields.Integer(
        string="Attendances",
        compute="_compute_attendance_count",
    )

    def _compute_membership_count(self):
        for rec in self:
            rec.membership_count = len(rec.membership_ids)

    def _compute_has_portal_user(self):
        for rec in self:
            rec.has_portal_user = bool(rec.user_ids.filtered("active"))

    def _compute_attendance_count(self):
        attendance_data = dict(
            self.env["gym.attendance"]._read_group(
                [("partner_id", "in", self.ids)],
                ["partner_id"],
                ["__count"],
            ),
        )
        for rec in self:
            rec.attendance_count = attendance_data.get(rec, 0)

    def action_view_memberships(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Memberships",
            "res_model": "gym.membership",
            "view_mode": "list,form",
            "domain": [("partner_id", "=", self.id)],
            "context": {"default_partner_id": self.id},
        }

    def action_view_attendance(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Attendance"),
            "res_model": "gym.attendance",
            "view_mode": "list,form",
            "domain": [("partner_id", "=", self.id)],
        }

    def action_create_portal_user(self):
        self.ensure_one()
        if not self.is_member:
            raise UserError(_("Portal access can only be created for active members."))
        if not self.email:
            raise UserError(_("Please set an email address for %s before creating a portal account.") % self.name)
        if self.user_ids.filtered("active"):
            raise UserError(_("%s already has a portal user account.") % self.name)

        company = self.company_id or self.env.company
        user = (
            self.env["res.users"]
            .sudo()
            .with_context(no_reset_password=True)
            ._create_user_from_template(
                {
                    "email": self.email,
                    "login": self.email,
                    "partner_id": self.id,
                    "company_id": company.id,
                    "company_ids": [Command.set(company.ids)],
                },
            )
        )
        user.partner_id.signup_prepare()

        template = self.env.ref("eb_gym_management.mail_template_portal_invitation", raise_if_not_found=False)
        if template:
            template.send_mail(self.id, force_send=True)
        self.message_post(body=_("Portal user account created and invitation email sent."))
