from uuid import UUID

from psycopg2 import IntegrityError
from odoo import fields, http
from odoo.http import request


def _json(data, status=200):
    return request.make_json_response(data, status=status)


def _body():
    payload = request.httprequest.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _require_api():
    if not request.env.user.has_group("violoop_facilities_api.group_violoop_api"):
        return _json({"error": "Violoop API Integration group required"}, 403)
    return None


def _uuid(value, field_name="event_id"):
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{field_name} must be a valid UUID")


def _serialize_interaction(record):
    return {
        "id": record.id,
        "uuid": record.uuid,
        "event_id": record.external_event_id or None,
        "channel": record.channel,
        "direction": record.direction,
        "actor_type": record.actor_type,
        "provider": record.provider or None,
        "provider_message_id": record.provider_message_id or None,
        "subject": record.subject or "",
        "body": record.body or "",
        "status": record.status,
        "occurred_at": fields.Datetime.to_string(record.occurred_at),
        "ai_generated": record.ai_generated,
        "metadata": record.metadata_json or {},
    }


def _serialize_conversation(record, include_interactions=False):
    payload = {
        "id": record.id,
        "uuid": record.uuid,
        "event_id": record.external_event_id or None,
        "name": record.name,
        "state": record.state,
        "priority": record.priority,
        "primary_channel": record.primary_channel,
        "ai_owner": record.ai_owner,
        "human_required": record.human_required,
        "unread_count": record.unread_count,
        "last_interaction_at": (
            fields.Datetime.to_string(record.last_interaction_at)
            if record.last_interaction_at else None
        ),
        "partner": {
            "id": record.partner_id.id,
            "name": record.partner_id.display_name,
            "email": record.partner_id.email or "",
            "phone": record.partner_id.phone or record.partner_id.mobile or "",
        } if record.partner_id else None,
        "lead": {
            "id": record.crm_lead_id.id,
            "name": record.crm_lead_id.name,
            "type": record.crm_lead_id.type,
        } if record.crm_lead_id else None,
        "facility_site_id": record.facility_site_id.id if record.facility_site_id else None,
        "assigned_user": {
            "id": record.assigned_user_id.id,
            "name": record.assigned_user_id.name,
        } if record.assigned_user_id else None,
    }
    if include_interactions:
        payload["interactions"] = [
            _serialize_interaction(item)
            for item in record.interaction_ids.sorted(
                key=lambda item: (item.occurred_at, item.id)
            )
        ]
    return payload


class VioloopConversationApi(http.Controller):
    @http.route(
        "/violoop/v1/conversations",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["GET"],
        csrf=False,
        save_session=False,
        readonly=True,
    )
    def list_conversations(self):
        denied = _require_api()
        if denied:
            return denied

        query = (request.httprequest.args.get("q") or "").strip()
        state = (request.httprequest.args.get("state") or "").strip()
        try:
            limit = max(1, min(int(request.httprequest.args.get("limit", "50")), 100))
        except ValueError:
            return _json({"error": "limit must be an integer"}, 400)

        domain = [
            ("company_id", "in", request.env.companies.ids),
            ("active", "=", True),
        ]
        if state:
            domain.append(("state", "=", state))
        if query:
            domain += [
                "|", "|",
                ("name", "ilike", query),
                ("partner_id.name", "ilike", query),
                ("crm_lead_id.name", "ilike", query),
            ]

        records = request.env["violoop.conversation"].search(domain, limit=limit)
        return _json({"items": [_serialize_conversation(record) for record in records]})

    @http.route(
        "/violoop/v1/conversations",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def create_conversation(self):
        denied = _require_api()
        if denied:
            return denied

        payload = _body()
        try:
            event_id = _uuid(payload.get("event_id"))
        except ValueError as exc:
            return _json({"error": str(exc)}, 400)

        name = str(payload.get("name") or "").strip()
        if not name:
            return _json({"error": "name is required"}, 400)

        Conversation = request.env["violoop.conversation"]
        existing = Conversation.search([("external_event_id", "=", event_id)], limit=1)
        if existing:
            return _json({**_serialize_conversation(existing), "replayed": True})

        partner = request.env["res.partner"]
        if payload.get("partner_id"):
            partner = partner.browse(int(payload["partner_id"])).exists()
            if not partner:
                return _json({"error": "partner was not found"}, 404)

        lead = request.env["crm.lead"]
        if payload.get("crm_lead_id"):
            lead = lead.browse(int(payload["crm_lead_id"])).exists()
            if not lead:
                return _json({"error": "CRM lead was not found"}, 404)

        site = request.env["violoop.facility.site"]
        if payload.get("facility_site_id"):
            site = site.browse(int(payload["facility_site_id"])).exists()
            if not site:
                return _json({"error": "facility site was not found"}, 404)

        channel = str(payload.get("primary_channel") or "internal")
        if channel not in {"email","sms","whatsapp","voice","webchat","internal"}:
            return _json({"error": "unsupported primary_channel"}, 400)

        priority = str(payload.get("priority") or "0")
        if priority not in {"0","1","2","3"}:
            return _json({"error": "priority must be 0, 1, 2 or 3"}, 400)

        ai_owner = str(payload.get("ai_owner") or "none")
        if ai_owner not in {"none","orbit","pulse","vector","halo"}:
            return _json({"error": "unsupported ai_owner"}, 400)

        values = {
            "external_event_id": event_id,
            "name": name[:255],
            "company_id": site.company_id.id if site else request.env.company.id,
            "facility_site_id": site.id if site else False,
            "partner_id": partner.id if partner else False,
            "crm_lead_id": lead.id if lead else False,
            "primary_channel": channel,
            "priority": priority,
            "ai_owner": ai_owner,
            "human_required": bool(payload.get("human_required", False)),
        }

        try:
            with request.env.cr.savepoint():
                record = Conversation.create(values)
        except IntegrityError:
            record = Conversation.search([("external_event_id", "=", event_id)], limit=1)
            if not record:
                raise

        return _json({**_serialize_conversation(record), "replayed": False}, 201)

    @http.route(
        "/violoop/v1/conversations/<string:conversation_uuid>",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["GET"],
        csrf=False,
        save_session=False,
        readonly=True,
    )
    def get_conversation(self, conversation_uuid):
        denied = _require_api()
        if denied:
            return denied

        record = request.env["violoop.conversation"].search([
            ("uuid", "=", conversation_uuid),
            ("company_id", "in", request.env.companies.ids),
        ], limit=1)
        if not record:
            return _json({"error": "conversation not found"}, 404)
        return _json(_serialize_conversation(record, True))

    @http.route(
        "/violoop/v1/conversations/<string:conversation_uuid>/interactions",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def create_interaction(self, conversation_uuid):
        denied = _require_api()
        if denied:
            return denied

        conversation = request.env["violoop.conversation"].search([
            ("uuid", "=", conversation_uuid),
            ("company_id", "in", request.env.companies.ids),
        ], limit=1)
        if not conversation:
            return _json({"error": "conversation not found"}, 404)

        payload = _body()
        try:
            event_id = _uuid(payload.get("event_id"))
        except ValueError as exc:
            return _json({"error": str(exc)}, 400)

        Interaction = request.env["violoop.interaction"]
        existing = Interaction.search([("external_event_id", "=", event_id)], limit=1)
        if existing:
            return _json({**_serialize_interaction(existing), "replayed": True})

        channel = str(payload.get("channel") or conversation.primary_channel)
        direction = str(payload.get("direction") or "internal")
        actor_type = str(payload.get("actor_type") or "human")
        if channel not in {"email","sms","whatsapp","voice","webchat","internal"}:
            return _json({"error": "unsupported channel"}, 400)
        if direction not in {"inbound","outbound","internal"}:
            return _json({"error": "unsupported direction"}, 400)
        if actor_type not in {"customer","human","agent","system"}:
            return _json({"error": "unsupported actor_type"}, 400)

        status = str(payload.get("status") or ("received" if direction == "inbound" else "queued"))
        if status not in {"received","queued","sent","delivered","read","failed"}:
            return _json({"error": "unsupported status"}, 400)

        values = {
            "external_event_id": event_id,
            "conversation_id": conversation.id,
            "channel": channel,
            "direction": direction,
            "actor_type": actor_type,
            "actor_user_id": (
                request.env["res.users"].browse(
                    int(payload.get("actor_user_id"))
                ).exists().id
                if actor_type == "human" and payload.get("actor_user_id")
                else request.env.user.id if actor_type == "human" else False
            ),
            "partner_id": conversation.partner_id.id
                if actor_type == "customer" and conversation.partner_id else False,
            "provider": str(payload.get("provider") or "")[:128],
            "provider_message_id": str(payload.get("provider_message_id") or "")[:255],
            "subject": str(payload.get("subject") or "")[:255],
            "body": str(payload.get("body") or "")[:20000],
            "status": status,
            "occurred_at": payload.get("occurred_at") or fields.Datetime.now(),
            "ai_generated": bool(payload.get("ai_generated", False)),
            "metadata_json": payload.get("metadata")
                if isinstance(payload.get("metadata"), dict) else {},
        }

        try:
            with request.env.cr.savepoint():
                interaction = Interaction.create(values)
        except IntegrityError:
            interaction = Interaction.search([("external_event_id", "=", event_id)], limit=1)
            if not interaction:
                raise

        return _json({**_serialize_interaction(interaction), "replayed": False}, 201)

    @http.route(
        "/violoop/v1/attention",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["GET"],
        csrf=False,
        save_session=False,
        readonly=True,
    )
    def attention(self):
        denied = _require_api()
        if denied:
            return denied

        records = request.env["violoop.conversation"].search([
            ("company_id", "in", request.env.companies.ids),
            ("active", "=", True),
            ("state", "!=", "closed"),
            "|", "|",
            ("unread_count", ">", 0),
            ("human_required", "=", True),
            ("state", "=", "approval_required"),
        ], order="priority desc, last_interaction_at desc, id desc", limit=50)

        return _json({"items": [{
            "kind": "conversation",
            "id": record.uuid,
            "priority": record.priority,
            "title": record.name,
            "state": record.state,
            "unread_count": record.unread_count,
            "human_required": record.human_required,
            "partner": record.partner_id.display_name if record.partner_id else None,
            "last_interaction_at": fields.Datetime.to_string(record.last_interaction_at)
                if record.last_interaction_at else None,
        } for record in records]})

    @http.route(
        "/violoop/v1/customers/<int:partner_id>/360",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["GET"],
        csrf=False,
        save_session=False,
        readonly=True,
    )
    def customer_360(self, partner_id):
        denied = _require_api()
        if denied:
            return denied

        partner = request.env["res.partner"].browse(partner_id).exists()
        if not partner:
            return _json({"error": "customer not found"}, 404)

        company_ids = request.env.companies.ids
        memberships = request.env["gym.membership"].search([
            ("partner_id", "=", partner.id),
            ("company_id", "in", company_ids),
        ], order="id desc", limit=10)
        leads = request.env["crm.lead"].search([
            ("partner_id", "=", partner.id),
            ("company_id", "in", company_ids),
        ], order="write_date desc", limit=20)
        conversations = request.env["violoop.conversation"].search([
            ("partner_id", "=", partner.id),
            ("company_id", "in", company_ids),
        ], order="last_interaction_at desc, id desc", limit=20)
        attendances = request.env["gym.attendance"].search([
            ("partner_id", "=", partner.id),
            ("company_id", "in", company_ids),
        ], order="check_in desc", limit=20)

        return _json({
            "partner": {
                "id": partner.id,
                "name": partner.display_name,
                "email": partner.email or "",
                "phone": partner.phone or partner.mobile or "",
            },
            "memberships": [{
                "id": item.id,
                "reference": item.name,
                "state": item.state,
                "plan": item.plan_id.display_name,
                "end_date": fields.Date.to_string(item.end_date) if item.end_date else None,
            } for item in memberships],
            "crm": [{
                "id": item.id,
                "name": item.name,
                "type": item.type,
                "stage": item.stage_id.name if item.stage_id else None,
                "expected_revenue": item.expected_revenue,
            } for item in leads],
            "conversations": [_serialize_conversation(item) for item in conversations],
            "attendance": [{
                "id": item.id,
                "check_in": fields.Datetime.to_string(item.check_in) if item.check_in else None,
                "check_out": fields.Datetime.to_string(item.check_out) if item.check_out else None,
            } for item in attendances],
        })
