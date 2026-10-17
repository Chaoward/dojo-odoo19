from uuid import uuid4

from odoo import api, fields, models

CHANNELS = [
    ("email", "Email"),
    ("sms", "SMS"),
    ("whatsapp", "WhatsApp"),
    ("voice", "Voice"),
    ("webchat", "Web Chat"),
    ("internal", "Internal"),
]


class VioloopConversation(models.Model):
    _name = "violoop.conversation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Violoop Conversation"
    _order = "priority desc, last_interaction_at desc, id desc"
    _check_company_auto = True

    uuid = fields.Char(required=True, readonly=True, copy=False, index=True,
        default=lambda self: str(uuid4()))
    external_event_id = fields.Char(copy=False, index=True)
    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    state = fields.Selection([
        ("open", "Open"),
        ("waiting_customer", "Waiting for Customer"),
        ("waiting_internal", "Waiting Internal"),
        ("approval_required", "Approval Required"),
        ("closed", "Closed"),
    ], default="open", required=True, tracking=True, index=True)
    priority = fields.Selection([
        ("0", "Normal"), ("1", "Elevated"), ("2", "High"), ("3", "Urgent")
    ], default="0", required=True, index=True)
    company_id = fields.Many2one("res.company", required=True,
        default=lambda self: self.env.company, index=True)
    facility_site_id = fields.Many2one("violoop.facility.site",
        string="Facility", check_company=True, index=True)
    partner_id = fields.Many2one("res.partner", string="Customer / Member",
        check_company=True, index=True)
    crm_lead_id = fields.Many2one("crm.lead", string="CRM Lead / Opportunity",
        check_company=True, index=True)
    assigned_user_id = fields.Many2one("res.users", string="Owner",
        tracking=True, check_company=True)
    assigned_team_id = fields.Many2one("crm.team", string="Sales Team",
        check_company=True)
    primary_channel = fields.Selection(CHANNELS, default="internal",
        required=True, index=True)
    ai_owner = fields.Selection([
        ("none", "None"), ("orbit", "Orbit"), ("pulse", "Pulse"),
        ("vector", "Vector"), ("halo", "Halo"),
    ], default="none", required=True)
    human_required = fields.Boolean(default=False, index=True)
    unread_count = fields.Integer(default=0)
    last_interaction_at = fields.Datetime(index=True)
    closed_at = fields.Datetime()
    interaction_ids = fields.One2many("violoop.interaction", "conversation_id")
    call_session_ids = fields.One2many("violoop.call.session", "conversation_id")

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Conversation UUID must be unique.")
    _external_event_unique = models.Constraint(
        "UNIQUE(external_event_id)",
        "Conversation external event ID must be unique.",
    )

    def write(self, values):
        values = dict(values)
        if values.get("state") == "closed" and "closed_at" not in values:
            values["closed_at"] = fields.Datetime.now()
        elif values.get("state") and values["state"] != "closed":
            values.setdefault("closed_at", False)
        return super().write(values)

    def _touch_from_interaction(self, interaction):
        self.ensure_one()
        values = {"last_interaction_at": interaction.occurred_at}
        if interaction.direction == "inbound":
            values["unread_count"] = self.unread_count + 1
            if self.state == "closed":
                values["state"] = "open"
        self.write(values)


class VioloopInteraction(models.Model):
    _name = "violoop.interaction"
    _description = "Violoop Interaction Ledger"
    _order = "occurred_at asc, id asc"
    _check_company_auto = True

    uuid = fields.Char(required=True, readonly=True, copy=False, index=True,
        default=lambda self: str(uuid4()))
    external_event_id = fields.Char(copy=False, index=True)
    conversation_id = fields.Many2one("violoop.conversation", required=True,
        ondelete="cascade", index=True, check_company=True)
    company_id = fields.Many2one(related="conversation_id.company_id", store=True, index=True)
    channel = fields.Selection(CHANNELS, required=True, index=True)
    direction = fields.Selection([
        ("inbound", "Inbound"), ("outbound", "Outbound"), ("internal", "Internal")
    ], required=True, index=True)
    actor_type = fields.Selection([
        ("customer", "Customer"), ("human", "Human"),
        ("agent", "AI Agent"), ("system", "System"),
    ], default="human", required=True)
    actor_user_id = fields.Many2one("res.users", check_company=True)
    partner_id = fields.Many2one("res.partner", check_company=True)
    provider = fields.Char(index=True)
    provider_message_id = fields.Char(index=True)
    subject = fields.Char()
    body = fields.Text()
    status = fields.Selection([
        ("received", "Received"), ("queued", "Queued"), ("sent", "Sent"),
        ("delivered", "Delivered"), ("read", "Read"), ("failed", "Failed"),
    ], default="received", required=True, index=True)
    occurred_at = fields.Datetime(required=True, default=fields.Datetime.now, index=True)
    ai_generated = fields.Boolean(default=False)
    metadata_json = fields.Json(default=dict)

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Interaction UUID must be unique.")
    _external_event_unique = models.Constraint(
        "UNIQUE(external_event_id)",
        "Interaction external event ID must be unique.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record.conversation_id._touch_from_interaction(record)
        return records


class VioloopChannelIdentity(models.Model):
    _name = "violoop.channel.identity"
    _description = "Violoop Channel Identity"
    _check_company_auto = True

    partner_id = fields.Many2one("res.partner", required=True, ondelete="cascade",
        index=True, check_company=True)
    company_id = fields.Many2one("res.company", required=True,
        default=lambda self: self.env.company, index=True)
    kind = fields.Selection([
        ("email", "Email"), ("phone", "Phone"),
        ("whatsapp", "WhatsApp"), ("web", "Web Identity"),
    ], required=True, index=True)
    value = fields.Char(required=True)
    normalized_value = fields.Char(required=True, index=True)
    provider = fields.Char()
    verified = fields.Boolean(default=False)

    _identity_unique = models.Constraint(
        "UNIQUE(company_id, kind, normalized_value)",
        "This channel identity already exists in this company.",
    )


class VioloopCallSession(models.Model):
    _name = "violoop.call.session"
    _description = "Violoop Call Session"
    _order = "started_at desc, id desc"
    _check_company_auto = True

    uuid = fields.Char(required=True, readonly=True, copy=False, index=True,
        default=lambda self: str(uuid4()))
    conversation_id = fields.Many2one("violoop.conversation", required=True,
        ondelete="cascade", index=True, check_company=True)
    company_id = fields.Many2one(related="conversation_id.company_id", store=True, index=True)
    partner_id = fields.Many2one(related="conversation_id.partner_id", store=True, index=True)
    direction = fields.Selection([("inbound", "Inbound"), ("outbound", "Outbound")],
        required=True)
    state = fields.Selection([
        ("incoming", "Incoming"), ("outgoing", "Outgoing"),
        ("connecting", "Connecting"), ("connected", "Connected"),
        ("held", "Held"), ("transferring", "Transferring"),
        ("ended", "Ended"), ("failed", "Failed"),
    ], required=True, default="incoming", index=True)
    from_address = fields.Char()
    to_address = fields.Char()
    provider = fields.Char(default="telnyx", index=True)
    provider_call_id = fields.Char(index=True)
    started_at = fields.Datetime(default=fields.Datetime.now, required=True)
    answered_at = fields.Datetime()
    ended_at = fields.Datetime()
    duration_seconds = fields.Integer(default=0)
    recording_reference = fields.Char()
    transcript_reference = fields.Char()
    summary = fields.Text()
    outcome = fields.Char()
    metadata_json = fields.Json(default=dict)

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Call session UUID must be unique.")


class VioloopApprovalRequest(models.Model):
    _name = "violoop.approval.request"
    _description = "Violoop Tool Approval Request"
    _order = "create_date desc, id desc"
    _check_company_auto = True

    uuid = fields.Char(required=True, readonly=True, copy=False, index=True,
        default=lambda self: str(uuid4()))
    company_id = fields.Many2one("res.company", required=True,
        default=lambda self: self.env.company, index=True)
    requested_by_id = fields.Many2one("res.users", required=True,
        default=lambda self: self.env.user, check_company=True)
    resolved_by_id = fields.Many2one("res.users", check_company=True)
    tool_name = fields.Char(required=True, index=True)
    provider = fields.Char(index=True)
    risk = fields.Selection([
        ("read", "Read"), ("low", "Low"), ("business", "Business"),
        ("financial", "Financial"), ("security", "Security"),
    ], required=True, index=True)
    state = fields.Selection([
        ("pending", "Pending"), ("approved", "Approved"),
        ("rejected", "Rejected"), ("executed", "Executed"), ("expired", "Expired"),
    ], default="pending", required=True, index=True)
    work_scope_json = fields.Json(default=dict)
    arguments_json = fields.Json(default=dict)
    idempotency_key = fields.Char(index=True)
    reason = fields.Text()
    resolved_at = fields.Datetime()
    executed_at = fields.Datetime()

    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Approval UUID must be unique.")

    def action_approve(self):
        self.write({
            "state": "approved",
            "resolved_by_id": self.env.user.id,
            "resolved_at": fields.Datetime.now(),
        })

    def action_reject(self):
        self.write({
            "state": "rejected",
            "resolved_by_id": self.env.user.id,
            "resolved_at": fields.Datetime.now(),
        })
