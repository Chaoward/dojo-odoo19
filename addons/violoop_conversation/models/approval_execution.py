from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from odoo import fields, models
from odoo.exceptions import ValidationError


def _utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class VioloopApprovalRequest(models.Model):
    _inherit = "violoop.approval.request"

    approval_capability = fields.Char(index=True)
    input_hash = fields.Char(required=True, index=True, copy=False)
    expires_at = fields.Datetime(required=True, index=True)
    separation_of_duties = fields.Boolean(default=False)
    executed_by_id = fields.Many2one(
        "res.users",
        check_company=True,
    )
    provider_request_id = fields.Char(index=True)

    _input_hash_format = models.Constraint(
        "CHECK(char_length(input_hash) = 64)",
        "Approval input hash must be a SHA-256 hex digest.",
    )

    def _expire_if_needed(self):
        now = _utcnow_naive()
        for record in self:
            if (
                record.state in {"pending", "approved"}
                and record.expires_at
                and record.expires_at <= now
            ):
                record.write({"state": "expired"})

    def resolve_for_operator(self, operator, decision):
        self.ensure_one()
        self._expire_if_needed()
        if self.state != "pending":
            raise ValidationError(
                "Only pending approval requests can be resolved."
            )
        if decision not in {"approved", "rejected"}:
            raise ValidationError("Invalid approval decision.")
        if (
            decision == "approved"
            and self.separation_of_duties
            and operator == self.requested_by_id
        ):
            raise ValidationError(
                "This approval requires a different operator from the requester."
            )
        self.write(
            {
                "state": decision,
                "resolved_by_id": operator.id,
                "resolved_at": fields.Datetime.now(),
            }
        )

    def mark_executed(
        self,
        *,
        operator,
        provider_request_id="",
    ):
        self.ensure_one()
        self._expire_if_needed()
        if self.state != "approved":
            raise ValidationError(
                "Only an approved, unexpired request can be executed."
            )
        self.write(
            {
                "state": "executed",
                "executed_by_id": operator.id,
                "executed_at": fields.Datetime.now(),
                "provider_request_id": provider_request_id or False,
            }
        )


class VioloopToolReceipt(models.Model):
    _name = "violoop.tool.receipt"
    _description = "Violoop Tool Execution Receipt"
    _order = "started_at desc, id desc"
    _check_company_auto = True

    uuid = fields.Char(
        required=True,
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: str(uuid4()),
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        index=True,
    )
    operator_user_id = fields.Many2one(
        "res.users",
        required=True,
        check_company=True,
        index=True,
    )
    approval_id = fields.Many2one(
        "violoop.approval.request",
        check_company=True,
        index=True,
        ondelete="set null",
    )
    provider = fields.Char(required=True, index=True)
    tool_name = fields.Char(required=True, index=True)
    risk = fields.Selection(
        [
            ("read", "Read"),
            ("low", "Low"),
            ("business", "Business"),
            ("financial", "Financial"),
            ("security", "Security"),
        ],
        required=True,
        index=True,
    )
    state = fields.Selection(
        [
            ("running", "Running"),
            ("complete", "Complete"),
            ("failed", "Failed"),
        ],
        required=True,
        default="running",
        index=True,
    )
    idempotency_key = fields.Char(index=True)
    input_hash = fields.Char(required=True, index=True)
    output_hash = fields.Char(index=True)
    provider_request_id = fields.Char(index=True)
    summary = fields.Text()
    error_message = fields.Text()
    started_at = fields.Datetime(
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    completed_at = fields.Datetime()
    metadata_json = fields.Json(default=dict)

    _uuid_unique = models.Constraint(
        "UNIQUE(uuid)",
        "Tool receipt UUID must be unique.",
    )
    _tool_idempotency_unique = models.Constraint(
        "UNIQUE(company_id, tool_name, idempotency_key)",
        "A tool idempotency key can only be reserved once per company and tool.",
    )
