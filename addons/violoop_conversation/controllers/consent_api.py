from __future__ import annotations

from datetime import datetime, timezone

from odoo import fields, http
from odoo.http import request


def _json(data, status=200):
    return request.make_json_response(data, status=status)


def _require_api():
    if not request.env.user.has_group(
        "violoop_facilities_api.group_violoop_api"
    ):
        return _json({"error": "Violoop API Integration group required"}, 403)
    return None


class VioloopConsentApi(http.Controller):
    @http.route(
        "/violoop/v1/consent/check",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["GET"],
        csrf=False,
        save_session=False,
        readonly=True,
    )
    def check_consent(self):
        denied = _require_api()
        if denied:
            return denied

        args = request.httprequest.args
        try:
            partner_id = int(args.get("partner_id") or "0")
        except ValueError:
            return _json({"error": "partner_id must be an integer"}, 400)

        channel = str(args.get("channel") or "").strip()
        purpose = str(args.get("purpose") or "").strip()
        if partner_id < 1 or channel not in {
            "email", "sms", "whatsapp", "voice", "push"
        }:
            return _json({"error": "invalid partner/channel"}, 400)
        if purpose not in {"transactional", "service", "marketing"}:
            return _json({"error": "invalid consent purpose"}, 400)

        partner = request.env["res.partner"].browse(partner_id).exists()
        if not partner:
            return _json({"error": "partner not found"}, 404)

        evidence = request.env["violoop.communication.consent"].search(
            [
                ("partner_id", "=", partner.id),
                ("company_id", "in", request.env.companies.ids),
                ("channel", "=", channel),
                ("purpose", "=", purpose),
            ],
            order="captured_at desc, id desc",
            limit=1,
        )

        if not evidence:
            return _json(
                {
                    "granted": False,
                    "reason": "no recorded consent evidence",
                    "evidence_uuid": None,
                }
            )

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expired = bool(
            evidence.expires_at and evidence.expires_at <= now
        )
        granted = evidence.status == "granted" and not expired

        return _json(
            {
                "granted": granted,
                "reason": (
                    "granted"
                    if granted
                    else "expired" if expired else evidence.status
                ),
                "evidence_uuid": evidence.uuid,
                "captured_at": fields.Datetime.to_string(
                    evidence.captured_at
                ),
                "expires_at": (
                    fields.Datetime.to_string(evidence.expires_at)
                    if evidence.expires_at
                    else None
                ),
            }
        )
