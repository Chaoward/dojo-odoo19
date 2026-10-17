from odoo import api, fields, models


class DojoInteractionEvent(models.Model):
    _name = "dojo.interaction.event"
    _description = "Dojang Interaction Event"
    _order = "occurred_at desc, id desc"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        ondelete="cascade",
        index=True
    )
    source = fields.Selection(
        [
            ("odoo_chatter", "Odoo Chatter"),
            ("odoo_discuss", "Odoo Discuss"),
            ("odoo_phone", "Odoo Phone"),
            ("whatsmax", "WhatsMax"),
            ("telnyx", "Telnyx"),
            ("agentphone", "AgentPhone"),
            ("agentmail", "AgentMail"),
            ("livekit", "LiveKit"),
            ("marketing_card", "Marketing Card"),
            ("portal", "Portal"),
            ("device", "Device"),
            ("platform", "Platform"),
            ("federation", "Federation")
        ],
        required=True,
        index=True
    )
    source_id = fields.Char(required=True, index=True)
    source_thread_id = fields.Char(index=True)
    kind = fields.Selection(
        [
            ("message", "Message"),
            ("internal_note", "Internal Note"),
            ("field_change", "Field Change"),
            ("activity", "Activity"),
            ("call", "Call"),
            ("call_transcript", "Call Transcript"),
            ("email", "Email"),
            ("campaign_touch", "Campaign Touch"),
            ("marketing_card", "Marketing Card"),
            ("file", "File"),
            ("portal_action", "Portal Action"),
            ("ai_action", "AI Action"),
            ("approval", "Approval"),
            ("system_event", "System Event")
        ],
        required=True,
        index=True
    )
    direction = fields.Selection(
        [
            ("inbound", "Inbound"),
            ("outbound", "Outbound"),
            ("internal", "Internal")
        ],
        required=True,
        default="internal",
        index=True
    )
    channel = fields.Char(index=True)
    partner_id = fields.Many2one("res.partner", ondelete="set null", index=True)
    res_model = fields.Char(index=True)
    res_id = fields.Integer(index=True)
    classification = fields.Selection(
        [
            ("public", "Public"),
            ("partner", "Partner"),
            ("internal", "Internal"),
            ("confidential", "Confidential"),
            ("restricted", "Restricted")
        ],
        required=True,
        default="internal",
        index=True
    )
    attention_state = fields.Selection(
        [
            ("new", "New"),
            ("needs_reply", "Needs Reply"),
            ("waiting_external", "Waiting External"),
            ("waiting_internal", "Waiting Internal"),
            ("scheduled", "Scheduled"),
            ("approval_pending", "Approval Pending"),
            ("blocked", "Blocked"),
            ("done", "Done")
        ],
        required=True,
        default="new",
        index=True
    )
    summary = fields.Char()
    body_text = fields.Text()
    payload = fields.Json(default=dict)
    correlation_id = fields.Char(index=True)
    occurred_at = fields.Datetime(
        required=True,
        default=fields.Datetime.now,
        index=True
    )

    _source_event_unique = models.Constraint(
        "unique(company_id, source, source_id)",
        "This provider event has already been indexed."
    )

    @api.model
    def ingest(self, values):
        event = self.create(values)
        if values.get("payload", {}).get("significant"):
            event.project_significant_to_chatter()
        return event

    def project_significant_to_chatter(self):
        for event in self:
            if not event.res_model or not event.res_id:
                continue
            if event.res_model not in self.env:
                continue
            record = self.env[event.res_model].browse(event.res_id).exists()
            if not record or not hasattr(record, "message_post"):
                continue
            text = event.summary or event.body_text or f"{event.kind} from {event.source}"
            record.message_post(
                body=text,
                message_type="comment",
                subtype_xmlid="mail.mt_note"
            )
