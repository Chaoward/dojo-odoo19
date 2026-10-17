import hashlib
import hmac
import json
import time

from odoo import http
from odoo.http import request


class DojoPlatformApi(http.Controller):
    @staticmethod
    def _authenticate():
        params = request.env["ir.config_parameter"].sudo()
        secret = params.get_str("dojo.platform.api_secret")
        if not secret:
            return False

        timestamp = request.httprequest.headers.get("X-Dojang-Timestamp", "")
        signature = request.httprequest.headers.get("X-Dojang-Signature", "")
        try:
            parsed = int(timestamp)
        except (TypeError, ValueError):
            return False

        if abs(int(time.time()) - parsed) > 300:
            return False

        body = request.httprequest.get_data(cache=True) or b""
        expected = hmac.new(
            secret.encode("utf-8"),
            timestamp.encode("utf-8") + b"." + body,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    @http.route(
        "/dojo_platform/v1/interactions/ingest",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False
    )
    def interaction_ingest(self):
        if not self._authenticate():
            return request.make_json_response({"error": "unauthorized"}, status=401)

        try:
            payload = json.loads(request.httprequest.get_data(cache=True) or b"{}")
        except json.JSONDecodeError:
            return request.make_json_response({"error": "invalid_json"}, status=400)

        required = ["source", "source_id", "kind", "direction"]
        missing = [name for name in required if not payload.get(name)]
        if missing:
            return request.make_json_response(
                {"error": "missing_fields", "fields": missing},
                status=400
            )

        event = request.env["dojo.interaction.event"].sudo().ingest(payload)
        return request.make_json_response({"id": event.id}, status=201)

    @http.route(
        "/dojo_platform/v1/interactions/timeline",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False
    )
    def interaction_timeline(self):
        if not self._authenticate():
            return request.make_json_response({"error": "unauthorized"}, status=401)

        try:
            payload = json.loads(request.httprequest.get_data(cache=True) or b"{}")
        except json.JSONDecodeError:
            return request.make_json_response({"error": "invalid_json"}, status=400)

        domain = [("company_id", "=", request.env.company.id)]
        if payload.get("res_model") and payload.get("res_id"):
            domain += [
                ("res_model", "=", payload["res_model"]),
                ("res_id", "=", int(payload["res_id"]))
            ]
        if payload.get("partner_id"):
            domain.append(("partner_id", "=", int(payload["partner_id"])))

        rows = request.env["dojo.interaction.event"].sudo().search(
            domain,
            order="occurred_at desc, id desc",
            limit=min(int(payload.get("limit", 100)), 200)
        )
        return request.make_json_response(
            {
                "events": [
                    {
                        "id": row.id,
                        "source": row.source,
                        "source_id": row.source_id,
                        "kind": row.kind,
                        "direction": row.direction,
                        "channel": row.channel,
                        "partner_id": row.partner_id.id or None,
                        "res_model": row.res_model,
                        "res_id": row.res_id,
                        "classification": row.classification,
                        "attention_state": row.attention_state,
                        "summary": row.summary,
                        "body_text": row.body_text,
                        "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None
                    }
                    for row in rows
                ]
            }
        )
