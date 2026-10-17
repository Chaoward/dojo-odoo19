from __future__ import annotations

import hashlib

from odoo import fields, http
from odoo.exceptions import ValidationError
from odoo.http import request


def _json(data, status=200):
    return request.make_json_response(data, status=status)


def _body():
    payload = request.httprequest.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _require_api():
    if not request.env.user.has_group(
        "violoop_facilities_api.group_violoop_api"
    ):
        return _json({"error": "Violoop API Integration group required"}, 403)
    return None


def _sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class VioloopIdentityApi(http.Controller):
    @http.route(
        "/violoop/v1/operators/<int:user_id>/profile",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["GET"],
        csrf=False,
        save_session=False,
        readonly=True,
    )
    def operator_profile(self, user_id):
        denied = _require_api()
        if denied:
            return denied

        user = request.env["res.users"].browse(user_id).exists()
        if not user:
            return _json({"error": "operator not found"}, 404)

        company_id = request.httprequest.args.get("company_id")
        facility_site_id = request.httprequest.args.get("facility_site_id")
        try:
            profile = user.violoop_profile(
                company_id=int(company_id) if company_id else None,
                facility_site_id=(
                    int(facility_site_id) if facility_site_id else None
                ),
                include_private=True,
            )
        except (ValueError, ValidationError) as exc:
            return _json({"error": str(exc)}, 403)

        return _json(profile)

    @http.route(
        "/violoop/v1/operator-sessions",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def create_operator_session(self):
        denied = _require_api()
        if denied:
            return denied

        payload = _body()
        try:
            user_id = int(payload["user_id"])
            company_id = int(payload["company_id"])
            jti = str(payload["jti"])
            expires_at = fields.Datetime.to_datetime(payload["expires_at"])
        except (KeyError, TypeError, ValueError) as exc:
            return _json({"error": f"invalid session payload: {exc}"}, 400)

        if len(jti) < 24:
            return _json({"error": "session token identifier is too short"}, 400)

        user = request.env["res.users"].browse(user_id).exists()
        company = request.env["res.company"].browse(company_id).exists()
        if not user or not company or company not in user.company_ids:
            return _json({"error": "invalid operator/company scope"}, 403)

        try:
            user.violoop_profile(company_id=company.id)
        except ValidationError as exc:
            return _json({"error": str(exc)}, 403)

        session = request.env["violoop.operator.session"].create(
            {
                "jti_hash": _sha256(jti),
                "user_id": user.id,
                "company_id": company.id,
                "expires_at": expires_at,
                "user_agent_label": str(
                    payload.get("user_agent_label") or ""
                )[:255],
                "source": str(payload.get("source") or "control_web"),
            }
        )
        return _json(
            {
                "uuid": session.uuid,
                "created_at": fields.Datetime.to_string(session.created_at),
                "expires_at": fields.Datetime.to_string(session.expires_at),
            },
            201,
        )

    @http.route(
        "/violoop/v1/operator-sessions/check",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def check_operator_session(self):
        denied = _require_api()
        if denied:
            return denied

        payload = _body()
        jti = str(payload.get("jti") or "")
        if not jti:
            return _json({"error": "jti is required"}, 400)

        session = request.env["violoop.operator.session"].search(
            [("jti_hash", "=", _sha256(jti))],
            limit=1,
        )
        if not session or not session.is_active_now():
            return _json({"active": False}, 401)

        session.write({"last_seen_at": fields.Datetime.now()})
        facility_site_id = payload.get("facility_site_id")
        try:
            profile = session.user_id.violoop_profile(
                company_id=session.company_id.id,
                facility_site_id=(
                    int(facility_site_id) if facility_site_id else None
                ),
                include_private=True,
            )
        except ValidationError as exc:
            return _json({"active": False, "error": str(exc)}, 403)

        return _json(
            {
                "active": True,
                "session_uuid": session.uuid,
                "profile": profile,
            }
        )

    @http.route(
        "/violoop/v1/operator-sessions/revoke",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def revoke_operator_session(self):
        denied = _require_api()
        if denied:
            return denied

        payload = _body()
        jti = str(payload.get("jti") or "")
        if not jti:
            return _json({"error": "jti is required"}, 400)

        session = request.env["violoop.operator.session"].search(
            [("jti_hash", "=", _sha256(jti))],
            limit=1,
        )
        if session and not session.revoked_at:
            session.write({"revoked_at": fields.Datetime.now()})
        return _json({"revoked": bool(session)})
