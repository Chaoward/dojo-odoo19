# -*- coding: utf-8 -*-
from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _compute_payment_state(self):
        """After payment state is recomputed, auto-activate / apply renewals."""
        super()._compute_payment_state()
        # sudo(): payment/reconciliation can run under a different active
        # company than the invoice itself, so don't rely on the branch
        # record rule here - scope explicitly to the invoices' own companies.
        memberships = (
            self.env["gym.membership"]
            .sudo()
            .search(
                [
                    ("sale_order_id.invoice_ids", "in", self.ids),
                    ("company_id", "in", self.mapped("company_id").ids),
                    "|",
                    ("state", "=", "draft"),
                    ("pending_renewal_end_date", "!=", False),
                ],
            )
        )
        if memberships:
            memberships._auto_activate_on_payment()
