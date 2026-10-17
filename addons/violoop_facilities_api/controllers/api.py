from datetime import timedelta
from functools import wraps
from uuid import UUID

from markupsafe import escape
from psycopg2 import IntegrityError

from odoo import fields, http
from odoo.http import request


def _json(data, status=200):
    return request.make_json_response(data, status=status)


def _api_only(method):
    @wraps(method)
    def wrapped(*args, **kwargs):
        if not request.env.user.has_group(
            "violoop_facilities_api.group_violoop_api"
        ):
            return _json({"error": "Violoop API Integration group required"}, 403)
        return method(*args, **kwargs)

    return wrapped


def _body():
    payload = request.httprequest.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _uuid(value, field_name="event_id"):
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{field_name} must be a valid UUID")


def _int(value, field_name, minimum=1):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be an integer")
    if parsed < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}")
    return parsed


def _iso_datetime(value, field_name):
    if value in (None, "", False):
        return False
    try:
        return fields.Datetime.to_datetime(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be an ISO datetime")


def _site(site_id):
    if not site_id:
        return request.env["violoop.facility.site"]
    parsed = _int(site_id, "facility_site_id")
    return request.env["violoop.facility.site"].search(
        [
            ("id", "=", parsed),
            ("company_id", "in", request.env.companies.ids),
        ],
        limit=1,
    )


def _serialize_site(site):
    return {
        "id": site.id,
        "name": site.name,
        "code": site.code,
        "timezone": site.timezone,
        "latitude": site.latitude,
        "longitude": site.longitude,
        "altitude_m": site.altitude_m,
        "niantic_site_id": site.niantic_site_id or None,
    }


def _serialize_maintenance(rec):
    return {
        "id": rec.id,
        "event_id": rec.external_event_id or None,
        "name": rec.name,
        "description": rec.description or "",
        "state": rec.state,
        "priority": rec.priority or "0",
        "maintenance_type": rec.maintenance_type,
        "source": rec.source,
        "facility_site": _serialize_site(rec.facility_site_id)
        if rec.facility_site_id
        else None,
        "equipment": {
            "id": rec.equipment_id.id,
            "name": rec.equipment_id.display_name,
        }
        if rec.equipment_id
        else None,
        "schedule_date": fields.Datetime.to_string(rec.schedule_date)
        if rec.schedule_date
        else None,
        "ai_risk": rec.ai_risk,
        "ai_summary": rec.ai_summary or "",
    }


def _serialize_lead(lead):
    return {
        "id": lead.id,
        "event_id": lead.violoop_external_event_id or None,
        "name": lead.name,
        "type": lead.type,
        "active": lead.active,
        "priority": lead.priority or "0",
        "probability": lead.probability,
        "expected_revenue": lead.expected_revenue,
        "stage": {
            "id": lead.stage_id.id,
            "name": lead.stage_id.name,
            "is_won": lead.stage_id.is_won,
        }
        if lead.stage_id
        else None,
        "contact": {
            "name": lead.contact_name or lead.partner_name or "",
            "email": lead.email_from or "",
            "phone": lead.phone or "",
            "partner_id": lead.partner_id.id if lead.partner_id else None,
        },
        "salesperson": {
            "id": lead.user_id.id,
            "name": lead.user_id.name,
        }
        if lead.user_id
        else None,
        "team": {
            "id": lead.team_id.id,
            "name": lead.team_id.name,
        }
        if lead.team_id
        else None,
        "source": lead.violoop_source,
        "ai_summary": lead.violoop_ai_summary or "",
        "write_date": fields.Datetime.to_string(lead.write_date)
        if lead.write_date
        else None,
    }


class VioloopApi(http.Controller):
    @http.route(
        "/violoop/v1/overview",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["GET"],
        csrf=False,
        save_session=False,
        readonly=True,
    )
    @_api_only
    def overview(self):
        company_ids = request.env.companies.ids
        Membership = request.env["gym.membership"]
        Attendance = request.env["gym.attendance"]
        Maintenance = request.env["maintenance.request"]
        Site = request.env["violoop.facility.site"]
        Node = request.env["violoop.edge.node"]
        Lead = request.env["crm.lead"]

        active_memberships = Membership.search_count(
            [("company_id", "in", company_ids), ("state", "=", "active")]
        )
        checked_in = Attendance.search_count(
            [("company_id", "in", company_ids), ("check_out", "=", False)]
        )
        open_domain = [
            ("company_id", "in", company_ids),
            ("state", "not in", ["done", "cancelled"]),
        ]
        open_maintenance = Maintenance.search_count(open_domain)
        site_count = Site.search_count([("company_id", "in", company_ids)])
        online_cutoff = fields.Datetime.now() - timedelta(minutes=5)
        online_nodes = Node.search_count(
            [
                ("company_id", "in", company_ids),
                ("last_seen_at", ">=", online_cutoff),
            ]
        )
        open_crm_leads = Lead.search_count(
            [
                ("company_id", "in", company_ids),
                ("active", "=", True),
                ("type", "=", "lead"),
            ]
        )
        open_crm_opportunities = Lead.search_count(
            [
                ("company_id", "in", company_ids),
                ("active", "=", True),
                ("type", "=", "opportunity"),
                ("stage_id.is_won", "=", False),
            ]
        )
        issues = Maintenance.search(
            open_domain, order="priority desc, id desc", limit=8
        )

        return _json(
            {
                "tenant": {
                    "database": request.env.cr.dbname,
                    "companies": [
                        {"id": company.id, "name": company.name}
                        for company in request.env.companies
                    ],
                },
                "metrics": {
                    "active_memberships": active_memberships,
                    "currently_checked_in": checked_in,
                    "open_maintenance": open_maintenance,
                    "facility_sites": site_count,
                    "online_edge_nodes": online_nodes,
                    "open_crm_leads": open_crm_leads,
                    "open_crm_opportunities": open_crm_opportunities,
                },
                "issues": [_serialize_maintenance(issue) for issue in issues],
            }
        )

    @http.route(
        "/violoop/v1/facilities",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["GET"],
        csrf=False,
        save_session=False,
        readonly=True,
    )
    @_api_only
    def facilities(self):
        sites = request.env["violoop.facility.site"].search(
            [
                ("company_id", "in", request.env.companies.ids),
                ("active", "=", True),
            ],
            order="name",
        )
        return _json({"items": [_serialize_site(site) for site in sites]})

    @http.route(
        "/violoop/v1/members",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["GET"],
        csrf=False,
        save_session=False,
        readonly=True,
    )
    @_api_only
    def members(self):
        query = (request.httprequest.args.get("q") or "").strip()
        try:
            limit = max(
                1, min(int(request.httprequest.args.get("limit", "20")), 50)
            )
        except ValueError:
            return _json({"error": "limit must be an integer"}, 400)

        domain = [
            ("company_id", "in", request.env.companies.ids),
            ("state", "=", "active"),
        ]
        if query:
            domain += [
                "|",
                "|",
                ("partner_id.name", "ilike", query),
                ("partner_id.email", "ilike", query),
                ("partner_id.phone", "ilike", query),
            ]

        memberships = request.env["gym.membership"].search(
            domain, order="id desc", limit=limit
        )
        items = []
        seen = set()
        for membership in memberships:
            partner = membership.partner_id
            if partner.id in seen:
                continue
            seen.add(partner.id)
            items.append(
                {
                    "id": partner.id,
                    "name": partner.name,
                    "email": partner.email or "",
                    "phone": partner.phone or partner.mobile or "",
                    "membership": {
                        "id": membership.id,
                        "reference": membership.name,
                        "state": membership.state,
                        "plan": membership.plan_id.display_name,
                        "end_date": fields.Date.to_string(membership.end_date)
                        if membership.end_date
                        else None,
                    },
                }
            )
        return _json({"items": items})

    @http.route(
        "/violoop/v1/checkins",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    @_api_only
    def checkins(self):
        payload = _body()
        try:
            event_id = _uuid(payload.get("event_id"))
            member_id = _int(payload.get("member_id"), "member_id")
            check_in = _iso_datetime(payload.get("check_in"), "check_in")
        except ValueError as exc:
            return _json({"error": str(exc)}, 400)

        Attendance = request.env["gym.attendance"]
        existing = Attendance.search(
            [("external_event_id", "=", event_id)], limit=1
        )
        if existing:
            return _json(
                {
                    "id": existing.id,
                    "event_id": event_id,
                    "replayed": True,
                    "check_in": fields.Datetime.to_string(existing.check_in),
                }
            )

        membership = request.env["gym.membership"].search(
            [
                ("partner_id", "=", member_id),
                ("company_id", "in", request.env.companies.ids),
                ("state", "=", "active"),
            ],
            order="id desc",
            limit=1,
        )
        if not membership:
            return _json(
                {"error": "No active membership is available for this member"},
                409,
            )

        site = _site(payload.get("facility_site_id"))
        if payload.get("facility_site_id") and not site:
            return _json({"error": "Facility site was not found"}, 404)

        source = payload.get("source")
        if source not in {"kiosk", "mobile", "edge"}:
            source = "kiosk"

        values = {
            "partner_id": membership.partner_id.id,
            "membership_id": membership.id,
            "external_event_id": event_id,
            "facility_site_id": site.id if site else False,
            "source": source,
        }
        if check_in:
            values["check_in"] = check_in

        try:
            with request.env.cr.savepoint():
                attendance = Attendance.create(values)
        except IntegrityError:
            attendance = Attendance.search(
                [("external_event_id", "=", event_id)], limit=1
            )
            if not attendance:
                raise

        return _json(
            {
                "id": attendance.id,
                "event_id": event_id,
                "replayed": False,
                "member": membership.partner_id.name,
                "check_in": fields.Datetime.to_string(attendance.check_in),
            },
            201,
        )

    @http.route(
        "/violoop/v1/checkouts",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    @_api_only
    def checkouts(self):
        payload = _body()
        try:
            event_id = _uuid(payload.get("event_id"))
            member_id = _int(payload.get("member_id"), "member_id")
            check_out = (
                _iso_datetime(payload.get("check_out"), "check_out")
                or fields.Datetime.now()
            )
        except ValueError as exc:
            return _json({"error": str(exc)}, 400)

        Attendance = request.env["gym.attendance"]
        replay = Attendance.search(
            [("checkout_event_id", "=", event_id)], limit=1
        )
        if replay:
            return _json(
                {
                    "id": replay.id,
                    "event_id": event_id,
                    "replayed": True,
                    "check_out": fields.Datetime.to_string(replay.check_out),
                }
            )

        attendance = Attendance.search(
            [
                ("partner_id", "=", member_id),
                ("company_id", "in", request.env.companies.ids),
                ("check_out", "=", False),
            ],
            order="check_in desc",
            limit=1,
        )
        if not attendance:
            return _json(
                {"error": "No open attendance was found for this member"}, 409
            )

        try:
            with request.env.cr.savepoint():
                attendance.write(
                    {
                        "check_out": check_out,
                        "checkout_event_id": event_id,
                    }
                )
        except IntegrityError:
            replay = Attendance.search(
                [("checkout_event_id", "=", event_id)], limit=1
            )
            if replay:
                attendance = replay
            else:
                raise

        return _json(
            {
                "id": attendance.id,
                "event_id": event_id,
                "replayed": False,
                "check_out": fields.Datetime.to_string(attendance.check_out),
            }
        )

    @http.route(
        "/violoop/v1/maintenance",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["GET"],
        csrf=False,
        save_session=False,
        readonly=True,
    )
    @_api_only
    def maintenance_list(self):
        try:
            limit = max(
                1, min(int(request.httprequest.args.get("limit", "50")), 100)
            )
        except ValueError:
            return _json({"error": "limit must be an integer"}, 400)

        domain = [
            ("company_id", "in", request.env.companies.ids),
            ("state", "not in", ["done", "cancelled"]),
        ]
        site_id = request.httprequest.args.get("facility_site_id")
        if site_id:
            try:
                domain.append(
                    ("facility_site_id", "=", _int(site_id, "facility_site_id"))
                )
            except ValueError as exc:
                return _json({"error": str(exc)}, 400)

        records = request.env["maintenance.request"].search(
            domain, order="priority desc, id desc", limit=limit
        )
        return _json(
            {"items": [_serialize_maintenance(rec) for rec in records]}
        )

    @http.route(
        "/violoop/v1/maintenance",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    @_api_only
    def maintenance_create(self):
        payload = _body()
        try:
            event_id = _uuid(payload.get("event_id"))
        except ValueError as exc:
            return _json({"error": str(exc)}, 400)

        title = str(payload.get("name") or "").strip()
        if not title:
            return _json({"error": "name is required"}, 400)
        if len(title) > 240:
            return _json(
                {"error": "name must be at most 240 characters"}, 400
            )

        Maintenance = request.env["maintenance.request"]
        existing = Maintenance.search(
            [("external_event_id", "=", event_id)], limit=1
        )
        if existing:
            return _json(
                {**_serialize_maintenance(existing), "replayed": True}
            )

        site = _site(payload.get("facility_site_id"))
        if payload.get("facility_site_id") and not site:
            return _json({"error": "Facility site was not found"}, 404)

        equipment = request.env["maintenance.equipment"]
        if payload.get("equipment_id"):
            try:
                equipment_id = _int(
                    payload["equipment_id"],
                    "equipment_id",
                )
                equipment = equipment.search(
                    [
                        ("id", "=", equipment_id),
                        ("company_id", "in", request.env.companies.ids),
                    ],
                    limit=1,
                )
            except ValueError as exc:
                return _json({"error": str(exc)}, 400)
            if not equipment:
                return _json({"error": "Equipment was not found"}, 404)

        source = payload.get("source")
        allowed_sources = {
            "kiosk",
            "trace",
            "mobile",
            "spatial",
            "edge",
            "ai_assist",
        }
        if source not in allowed_sources:
            source = "edge"

        priority = str(payload.get("priority", "2"))
        if priority not in {"0", "1", "2", "3"}:
            return _json(
                {"error": "priority must be 0, 1, 2, or 3"}, 400
            )

        values = {
            "name": title,
            "description": str(
                escape(str(payload.get("description") or ""))
            ),
            "company_id": site.company_id.id
            if site
            else request.env.company.id,
            "facility_site_id": site.id if site else False,
            "equipment_id": equipment.id if equipment else False,
            "maintenance_type": payload.get("maintenance_type")
            if payload.get("maintenance_type")
            in {"corrective", "preventive"}
            else "corrective",
            "priority": priority,
            "external_event_id": event_id,
            "source": source,
            "capture_reference": str(
                payload.get("capture_reference") or ""
            )[:255],
        }

        try:
            with request.env.cr.savepoint():
                rec = Maintenance.create(values)
        except IntegrityError:
            rec = Maintenance.search(
                [("external_event_id", "=", event_id)], limit=1
            )
            if not rec:
                raise

        spatial = payload.get("spatial_anchor")
        if isinstance(spatial, dict) and site:
            required = [
                "anchor_uid",
                "position_x",
                "position_y",
                "position_z",
                "rotation_x",
                "rotation_y",
                "rotation_z",
                "rotation_w",
            ]
            missing = [
                key for key in required if spatial.get(key) is None
            ]
            if missing:
                return _json(
                    {
                        "error": "spatial_anchor is missing required fields",
                        "fields": missing,
                        "maintenance_id": rec.id,
                    },
                    400,
                )
            request.env["violoop.spatial.anchor"].create(
                {
                    "anchor_uid": str(spatial["anchor_uid"])[:255],
                    "name": str(
                        spatial.get("name") or title
                    )[:255],
                    "site_id": site.id,
                    "maintenance_request_id": rec.id,
                    "nsdk_site_id": str(
                        spatial.get("nsdk_site_id") or ""
                    )[:255],
                    "site_anchor_payload": str(
                        spatial.get("site_anchor_payload") or ""
                    ),
                    "position_x": float(spatial["position_x"]),
                    "position_y": float(spatial["position_y"]),
                    "position_z": float(spatial["position_z"]),
                    "rotation_x": float(spatial["rotation_x"]),
                    "rotation_y": float(spatial["rotation_y"]),
                    "rotation_z": float(spatial["rotation_z"]),
                    "rotation_w": float(spatial["rotation_w"]),
                    "source_device_uid": str(
                        spatial.get("source_device_uid") or ""
                    )[:255],
                    "metadata_json": spatial.get("metadata") or {},
                }
            )

        return _json(
            {**_serialize_maintenance(rec), "replayed": False}, 201
        )


    @http.route(
        "/violoop/v1/crm/leads",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["GET"],
        csrf=False,
        save_session=False,
        readonly=True,
    )
    @_api_only
    def crm_leads(self):
        query = (request.httprequest.args.get("q") or "").strip()
        try:
            limit = max(
                1,
                min(
                    int(request.httprequest.args.get("limit", "80")),
                    100,
                ),
            )
        except ValueError:
            return _json({"error": "limit must be an integer"}, 400)

        domain = [
            ("company_id", "in", request.env.companies.ids),
            ("active", "=", True),
        ]
        if query:
            domain += [
                "|",
                "|",
                "|",
                ("name", "ilike", query),
                ("contact_name", "ilike", query),
                ("email_from", "ilike", query),
                ("phone", "ilike", query),
            ]

        leads = request.env["crm.lead"].search(
            domain,
            order="priority desc, write_date desc, id desc",
            limit=limit,
        )
        return _json({"items": [_serialize_lead(lead) for lead in leads]})

    @http.route(
        "/violoop/v1/crm/leads",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    @_api_only
    def crm_lead_create(self):
        payload = _body()
        try:
            event_id = _uuid(payload.get("event_id"))
        except ValueError as exc:
            return _json({"error": str(exc)}, 400)

        Lead = request.env["crm.lead"]
        existing = Lead.search(
            [("violoop_external_event_id", "=", event_id)],
            limit=1,
        )
        if existing:
            return _json(
                {**_serialize_lead(existing), "replayed": True}
            )

        name = str(payload.get("name") or "").strip()
        if not name:
            return _json({"error": "name is required"}, 400)
        if len(name) > 240:
            return _json(
                {"error": "name must be at most 240 characters"},
                400,
            )

        lead_type = (
            payload.get("type")
            if payload.get("type") in {"lead", "opportunity"}
            else "lead"
        )
        priority = str(payload.get("priority", "0"))
        if priority not in {"0", "1", "2", "3"}:
            return _json(
                {"error": "priority must be 0, 1, 2, or 3"},
                400,
            )

        company_id = request.env.company.id
        team = request.env["crm.team"]
        if payload.get("team_id"):
            try:
                team = team.browse(
                    _int(payload["team_id"], "team_id")
                ).exists()
            except ValueError as exc:
                return _json({"error": str(exc)}, 400)
            if team and team.company_id:
                company_id = team.company_id.id

        values = {
            "name": name,
            "type": lead_type,
            "priority": priority,
            "company_id": company_id,
            "contact_name": str(
                payload.get("contact_name") or ""
            )[:255],
            "email_from": str(
                payload.get("email") or ""
            )[:255],
            "phone": str(payload.get("phone") or "")[:64],
            "description": str(
                escape(str(payload.get("description") or ""))
            ),
            "expected_revenue": max(
                0.0,
                float(payload.get("expected_revenue") or 0.0),
            ),
            "team_id": team.id if team else False,
            "violoop_external_event_id": event_id,
            "violoop_source": "console",
        }

        try:
            with request.env.cr.savepoint():
                lead = Lead.create(values)
        except IntegrityError:
            lead = Lead.search(
                [("violoop_external_event_id", "=", event_id)],
                limit=1,
            )
            if not lead:
                raise

        return _json(
            {**_serialize_lead(lead), "replayed": False},
            201,
        )

    @http.route(
        "/violoop/v1/crm/context",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["GET"],
        csrf=False,
        save_session=False,
        readonly=True,
    )
    @_api_only
    def crm_context(self):
        Lead = request.env["crm.lead"]
        company_domain = [
            ("company_id", "in", request.env.companies.ids),
            ("active", "=", True),
        ]
        lead_count = Lead.search_count(
            company_domain + [("type", "=", "lead")]
        )
        opportunity_domain = company_domain + [
            ("type", "=", "opportunity"),
            ("stage_id.is_won", "=", False),
        ]
        opportunity_count = Lead.search_count(opportunity_domain)
        focus = Lead.search(
            opportunity_domain,
            order=(
                "priority desc, probability desc, "
                "expected_revenue desc, write_date desc"
            ),
            limit=12,
        )
        return _json(
            {
                "metrics": {
                    "open_leads": lead_count,
                    "open_opportunities": opportunity_count,
                    "focus_expected_revenue": sum(
                        lead.expected_revenue for lead in focus
                    ),
                },
                "focus": [_serialize_lead(lead) for lead in focus],
                "metric_note": (
                    "focus_expected_revenue sums the 12 current "
                    "highest-focus opportunities, not the full pipeline."
                ),
            }
        )

    @http.route(
        "/violoop/v1/edge/heartbeat",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    @_api_only
    def edge_heartbeat(self):
        payload = _body()
        node_uid = str(payload.get("node_uid") or "").strip()
        node_name = str(payload.get("name") or node_uid).strip()
        if not node_uid or len(node_uid) > 255:
            return _json(
                {
                    "error": "node_uid is required and must be <=255 characters"
                },
                400,
            )

        site = request.env["violoop.facility.site"]
        site_code = str(payload.get("site_code") or "").strip()
        if site_code:
            site = site.search(
                [
                    ("code", "=", site_code),
                    ("company_id", "in", request.env.companies.ids),
                ],
                limit=1,
            )

        Node = request.env["violoop.edge.node"]
        node = Node.search([("node_uid", "=", node_uid)], limit=1)
        values = {
            "name": node_name[:255],
            "last_seen_at": fields.Datetime.now(),
            "status": "online",
            "software_version": str(
                payload.get("software_version") or ""
            )[:255],
            "capabilities_json": payload.get("capabilities") or {},
        }
        if site:
            values["site_id"] = site.id

        if node:
            node.write(values)
        else:
            node = Node.create({"node_uid": node_uid, **values})

        return _json(
            {
                "id": node.id,
                "node_uid": node.node_uid,
                "site_id": node.site_id.id if node.site_id else None,
                "last_seen_at": fields.Datetime.to_string(
                    node.last_seen_at
                ),
            }
        )
