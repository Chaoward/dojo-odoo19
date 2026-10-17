from __future__ import annotations

from uuid import uuid4

from odoo import fields, models


class VioloopCommunicationConsent(models.Model):
    _name = "violoop.communication.consent"
    _description = "Violoop Communication Consent Evidence"
    _order = "captured_at desc, id desc"
    _check_company_auto = True

    uuid = fields.Char(
        required=True,
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: str(uuid4()),
    )
    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="cascade",
        check_company=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    channel = fields.Selection(
        [
            ("email", "Email"),
            ("sms", "SMS"),
            ("whatsapp", "WhatsApp"),
            ("voice", "Voice"),
            ("push", "Push"),
        ],
        required=True,
        index=True,
    )
    purpose = fields.Selection(
        [
            ("transactional", "Transactional"),
            ("service", "Service"),
            ("marketing", "Marketing"),
        ],
        required=True,
        index=True,
    )
    status = fields.Selection(
        [
            ("granted", "Granted"),
            ("denied", "Denied"),
            ("revoked", "Revoked"),
        ],
        required=True,
        index=True,
    )
    source = fields.Selection(
        [
            ("member", "Member / Customer"),
            ("staff", "Staff Attestation"),
            ("import", "Verified Import"),
            ("provider", "Provider Preference"),
            ("system", "System"),
        ],
        required=True,
        default="member",
    )
    captured_at = fields.Datetime(
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    expires_at = fields.Datetime(index=True)
    external_reference = fields.Char(index=True)
    evidence_note = fields.Text()
    metadata_json = fields.Json(default=dict)

    _uuid_unique = models.Constraint(
        "UNIQUE(uuid)",
        "Consent evidence UUID must be unique.",
    )
