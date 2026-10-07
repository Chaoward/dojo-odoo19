# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_date


class GymMembershipRenewWizard(models.TransientModel):
    _name = "gym.membership.renew.wizard"
    _description = "Membership Renewal Wizard"

    membership_id = fields.Many2one(
        "gym.membership",
        string="Membership",
        required=True,
        readonly=True,
    )
    plan_id = fields.Many2one(
        "product.template",
        string="Plan",
        required=True,
        domain="[('is_gym_membership_plan', '=', True)]",
    )
    new_end_date = fields.Date(string="New End Date (Preview)", compute="_compute_new_end_date")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        membership_id = self.env.context.get("default_membership_id")
        if membership_id:
            membership = self.env["gym.membership"].browse(membership_id)
            res["membership_id"] = membership.id
            res["plan_id"] = membership.plan_id.id
        return res

    @api.depends("membership_id", "plan_id")
    def _compute_new_end_date(self):
        for rec in self:
            if rec.membership_id and rec.plan_id and rec.plan_id.gym_duration_value:
                current_end = rec.membership_id.end_date
                from_date = max(fields.Date.today(), current_end) if current_end else fields.Date.today()
                rec.new_end_date = rec.membership_id._plan_duration_end(from_date, rec.plan_id)
            else:
                rec.new_end_date = False

    def action_confirm_renewal(self):
        self.ensure_one()
        membership = self.membership_id
        if membership.state not in ("active", "expired"):
            raise UserError(_("Renewal is only available for Active or Expired memberships."))
        if membership.pending_renewal_end_date:
            raise UserError(
                _("A renewal is already pending payment for membership %s.") % membership.name,
            )

        product_product = self.plan_id.product_variant_id
        if not product_product:
            raise UserError(_("The selected Plan has no product variant. Please check the product configuration."))

        from_date = max(fields.Date.today(), membership.end_date or fields.Date.today())
        new_end = membership._plan_duration_end(from_date, self.plan_id)
        if not new_end:
            raise UserError(_("Unable to compute the new end date for the selected plan."))

        line_description = "%s — Renewal\n%s: %s → %s" % (
            self.plan_id.name,
            _("Period"),
            from_date.strftime("%d/%m/%Y"),
            new_end.strftime("%d/%m/%Y"),
        )

        # Create renewal Sales Order + Invoice.
        # sudo(): same rationale as action_confirm_membership() - a narrow,
        # well-defined business action gym staff can trigger without being
        # handed broad Sales/Accounting app permissions they shouldn't have.
        order = (
            self.env["sale.order"]
            .sudo()
            .create(
                {
                    "partner_id": membership.partner_id.id,
                    "company_id": membership.company_id.id,
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

        # Keep current access/end date until payment. Extension applies on payment.
        membership.write(
            {
                "sale_order_id": order.id,
                "pending_renewal_plan_id": self.plan_id.id,
                "pending_renewal_end_date": new_end,
            },
        )

        membership.message_post(
            body=_(
                "Renewal invoice created. New end date %s will apply after payment. Invoice: %s.",
            )
            % (format_date(self.env, new_end), order.invoice_ids[:1].name or order.name),
        )

        invoice = order.invoice_ids[:1]
        if invoice:
            return {
                "type": "ir.actions.act_window",
                "name": _("Renewal Invoice"),
                "res_model": "account.move",
                "view_mode": "form",
                "res_id": invoice.id,
                "target": "current",
            }
        return {"type": "ir.actions.act_window_close"}
