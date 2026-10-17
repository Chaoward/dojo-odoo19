from __future__ import annotations

from datetime import datetime, timezone

from odoo import fields, http
from odoo.exceptions import ValidationError
from odoo.http import request


_SCOPE_RANK = {"own": 1, "site": 2, "org": 3}


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


def _capability_satisfies(grant, required):
    try:
        gm, ga, gs = grant.split(".")
        rm, ra, rs = required.split(".")
    except ValueError:
        return False
    return (
        gm == rm
        and ga == ra
        and gs in _SCOPE_RANK
        and rs in _SCOPE_RANK
        and _SCOPE_RANK[gs] >= _SCOPE_RANK[rs]
    )


def _serialize_approval(record):
    record._expire_if_needed()
    return {
        "uuid": record.uuid,
        "state": record.state,
        "tool_name": record.tool_name,
        "provider": record.provider or "",
        "risk": record.risk,
        "approval_capability": record.approval_capability or None,
        "input_hash": record.input_hash,
        "idempotency_key": record.idempotency_key or None,
        "work_scope": record.work_scope_json or {},
        "arguments": record.arguments_json or {},
        "reason": record.reason or "",
        "separation_of_duties": record.separation_of_duties,
        "requested_by": {
            "id": record.requested_by_id.id,
            "name": record.requested_by_id.name,
        },
        "resolved_by": {
            "id": record.resolved_by_id.id,
            "name": record.resolved_by_id.name,
        }
        if record.resolved_by_id
        else None,
        "created_at": fields.Datetime.to_string(record.create_date),
        "expires_at": fields.Datetime.to_string(record.expires_at),
        "resolved_at": (
            fields.Datetime.to_string(record.resolved_at)
            if record.resolved_at
            else None
        ),
        "executed_at": (
            fields.Datetime.to_string(record.executed_at)
            if record.executed_at
            else None
        ),
        "provider_request_id": record.provider_request_id or None,
    }


class VioloopApprovalApi(http.Controller):
    @http.route(
        "/violoop/v1/approvals",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["GET"],
        csrf=False,
        save_session=False,
        readonly=True,
    )
    def list_approvals(self):
        denied = _require_api()
        if denied:
            return denied

        state = (request.httprequest.args.get("state") or "").strip()
        domain = [("company_id", "in", request.env.companies.ids)]
        if state:
            domain.append(("state", "=", state))
        records = request.env["violoop.approval.request"].search(
            domain,
            order="create_date desc, id desc",
            limit=100,
        )
        return _json(
            {"items": [_serialize_approval(record) for record in records]}
        )

    @http.route(
        "/violoop/v1/approvals",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def create_approval(self):
        denied = _require_api()
        if denied:
            return denied

        payload = _body()
        required = {
            "requested_by_id",
            "company_id",
            "tool_name",
            "provider",
            "risk",
            "input_hash",
            "expires_at",
        }
        missing = sorted(
            key for key in required if payload.get(key) in {None, ""}
        )
        if missing:
            return _json(
                {"error": f"missing approval fields: {', '.join(missing)}"},
                400,
            )

        try:
            user = request.env["res.users"].browse(
                int(payload["requested_by_id"])
            ).exists()
            company = request.env["res.company"].browse(
                int(payload["company_id"])
            ).exists()
            expires_at = fields.Datetime.to_datetime(payload["expires_at"])
        except (TypeError, ValueError) as exc:
            return _json({"error": f"invalid approval payload: {exc}"}, 400)

        if not user or not company or company not in user.company_ids:
            return _json({"error": "invalid requester/company scope"}, 403)
        if len(str(payload["input_hash"])) != 64:
            return _json({"error": "input_hash must be SHA-256 hex"}, 400)
        if expires_at <= datetime.now(timezone.utc).replace(tzinfo=None):
            return _json({"error": "approval expiry must be in the future"}, 400)

        idempotency_key = str(payload.get("idempotency_key") or "")
        if idempotency_key:
            existing = request.env["violoop.approval.request"].search(
                [
                    ("company_id", "=", company.id),
                    ("tool_name", "=", str(payload["tool_name"])),
                    ("idempotency_key", "=", idempotency_key),
                    ("input_hash", "=", str(payload["input_hash"])),
                ],
                limit=1,
            )
            if existing:
                return _json(
                    {**_serialize_approval(existing), "replayed": True}
                )

        record = request.env["violoop.approval.request"].create(
            {
                "company_id": company.id,
                "requested_by_id": user.id,
                "tool_name": str(payload["tool_name"])[:255],
                "provider": str(payload["provider"])[:128],
                "risk": str(payload["risk"]),
                "approval_capability": str(
                    payload.get("approval_capability") or ""
                )[:255],
                "input_hash": str(payload["input_hash"]),
                "idempotency_key": idempotency_key[:255],
                "work_scope_json": (
                    payload.get("work_scope")
                    if isinstance(payload.get("work_scope"), dict)
                    else {}
                ),
                "arguments_json": (
                    payload.get("arguments")
                    if isinstance(payload.get("arguments"), dict)
                    else {}
                ),
                "reason": str(payload.get("reason") or "")[:10000],
                "expires_at": expires_at,
                "separation_of_duties": bool(
                    payload.get("separation_of_duties", False)
                ),
            }
        )
        return _json(
            {**_serialize_approval(record), "replayed": False},
            201,
        )

    @http.route(
        "/violoop/v1/approvals/<string:approval_uuid>",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["GET"],
        csrf=False,
        save_session=False,
        readonly=True,
    )
    def get_approval(self, approval_uuid):
        denied = _require_api()
        if denied:
            return denied

        record = request.env["violoop.approval.request"].search(
            [
                ("uuid", "=", approval_uuid),
                ("company_id", "in", request.env.companies.ids),
            ],
            limit=1,
        )
        if not record:
            return _json({"error": "approval not found"}, 404)
        return _json(_serialize_approval(record))

    @http.route(
        "/violoop/v1/approvals/<string:approval_uuid>/resolve",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def resolve_approval(self, approval_uuid):
        denied = _require_api()
        if denied:
            return denied

        payload = _body()
        decision = str(payload.get("decision") or "")
        try:
            operator_id = int(payload.get("operator_user_id"))
        except (TypeError, ValueError):
            return _json({"error": "operator_user_id is required"}, 400)

        record = request.env["violoop.approval.request"].search(
            [
                ("uuid", "=", approval_uuid),
                ("company_id", "in", request.env.companies.ids),
            ],
            limit=1,
        )
        operator = request.env["res.users"].browse(operator_id).exists()
        if not record or not operator:
            return _json({"error": "approval or operator not found"}, 404)

        if decision == "approved" and record.approval_capability:
            facility_site_id = (
                record.work_scope_json.get("facilityId")
                if isinstance(record.work_scope_json, dict)
                else None
            )
            try:
                profile = operator.violoop_profile(
                    company_id=record.company_id.id,
                    facility_site_id=facility_site_id,
                )
            except ValidationError as exc:
                return _json({"error": str(exc)}, 403)

            if not any(
                _capability_satisfies(
                    grant,
                    record.approval_capability,
                )
                for grant in profile["capabilities"]
            ):
                return _json(
                    {
                        "error": (
                            "operator lacks approval capability: "
                            f"{record.approval_capability}"
                        )
                    },
                    403,
                )

        try:
            record.resolve_for_operator(operator, decision)
        except ValidationError as exc:
            return _json({"error": str(exc)}, 409)

        return _json(_serialize_approval(record))


class VioloopToolReceiptApi(http.Controller):
    @http.route(
        "/violoop/v1/tool-receipts/reserve",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def reserve_tool_receipt(self):
        denied = _require_api()
        if denied:
            return denied

        payload = _body()
        try:
            company_id = int(payload["company_id"])
            operator_user_id = int(payload["operator_user_id"])
        except (KeyError, TypeError, ValueError) as exc:
            return _json({"error": f"invalid receipt scope: {exc}"}, 400)

        tool_name = str(payload.get("tool_name") or "").strip()
        provider = str(payload.get("provider") or "").strip()
        risk = str(payload.get("risk") or "").strip()
        input_hash = str(payload.get("input_hash") or "").strip()
        idempotency_key = str(payload.get("idempotency_key") or "").strip()

        if not tool_name or not provider or not risk:
            return _json(
                {"error": "tool_name, provider and risk are required"},
                400,
            )
        if len(input_hash) != 64:
            return _json({"error": "input_hash must be SHA-256 hex"}, 400)

        # All provider mutations use a durable key. Read calls may supply a
        # generated request key from the edge so that every receipt is unique.
        if not idempotency_key:
            return _json({"error": "idempotency_key is required"}, 400)

        company = request.env["res.company"].browse(company_id).exists()
        operator = request.env["res.users"].browse(
            operator_user_id
        ).exists()
        if (
            not company
            or not operator
            or company not in operator.company_ids
        ):
            return _json({"error": "invalid operator/company scope"}, 403)

        Receipt = request.env["violoop.tool.receipt"]
        existing = Receipt.search(
            [
                ("company_id", "=", company.id),
                ("tool_name", "=", tool_name),
                ("idempotency_key", "=", idempotency_key),
            ],
            limit=1,
        )
        if existing:
            if existing.input_hash != input_hash:
                return _json(
                    {
                        "error": (
                            "idempotency key was already reserved with "
                            "different arguments"
                        )
                    },
                    409,
                )
            return _json(
                {
                    "replayed": True,
                    "uuid": existing.uuid,
                    "state": existing.state,
                    "provider_request_id": (
                        existing.provider_request_id or None
                    ),
                    "input_hash": existing.input_hash,
                    "output_hash": existing.output_hash or None,
                    "summary": existing.summary or "",
                    "error_message": existing.error_message or "",
                }
            )

        approval = request.env["violoop.approval.request"]
        approval_uuid = str(payload.get("approval_uuid") or "")
        if approval_uuid:
            approval = approval.search(
                [
                    ("uuid", "=", approval_uuid),
                    ("company_id", "=", company.id),
                ],
                limit=1,
            )
            if not approval:
                return _json({"error": "approval not found"}, 404)
            approval._expire_if_needed()
            if approval.state != "approved":
                return _json(
                    {"error": "approval is not currently approved"},
                    409,
                )
            if approval.input_hash != input_hash:
                return _json(
                    {"error": "approval hash does not match tool input"},
                    409,
                )

        receipt = Receipt.create(
            {
                "company_id": company.id,
                "operator_user_id": operator.id,
                "approval_id": approval.id if approval else False,
                "provider": provider[:128],
                "tool_name": tool_name[:255],
                "risk": risk,
                "state": "running",
                "idempotency_key": idempotency_key[:255],
                "input_hash": input_hash,
                "metadata_json": (
                    payload.get("metadata")
                    if isinstance(payload.get("metadata"), dict)
                    else {}
                ),
            }
        )

        return _json(
            {
                "replayed": False,
                "uuid": receipt.uuid,
                "state": receipt.state,
                "input_hash": receipt.input_hash,
            },
            201,
        )

    @http.route(
        "/violoop/v1/tool-receipts/<string:receipt_uuid>/complete",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def complete_tool_receipt(self, receipt_uuid):
        denied = _require_api()
        if denied:
            return denied

        payload = _body()
        state = str(payload.get("state") or "")
        if state not in {"complete", "failed"}:
            return _json(
                {"error": "state must be complete or failed"},
                400,
            )

        receipt = request.env["violoop.tool.receipt"].search(
            [
                ("uuid", "=", receipt_uuid),
                ("company_id", "in", request.env.companies.ids),
            ],
            limit=1,
        )
        if not receipt:
            return _json({"error": "tool receipt not found"}, 404)

        if receipt.state == "complete":
            return _json(
                {
                    "uuid": receipt.uuid,
                    "state": receipt.state,
                    "replayed": True,
                }
            )
        if receipt.state != "running":
            return _json(
                {
                    "error": (
                        "only a running tool receipt can be finalized; "
                        f"current state is {receipt.state}"
                    )
                },
                409,
            )

        output_hash = str(payload.get("output_hash") or "")
        if output_hash and len(output_hash) != 64:
            return _json({"error": "output_hash must be SHA-256 hex"}, 400)

        receipt.write(
            {
                "state": state,
                "output_hash": output_hash or False,
                "provider_request_id": str(
                    payload.get("provider_request_id") or ""
                )[:255],
                "summary": str(payload.get("summary") or "")[:10000],
                "error_message": str(
                    payload.get("error_message") or ""
                )[:10000],
                "completed_at": fields.Datetime.now(),
            }
        )

        if receipt.approval_id and state == "complete":
            try:
                receipt.approval_id.mark_executed(
                    operator=receipt.operator_user_id,
                    provider_request_id=(
                        receipt.provider_request_id or ""
                    ),
                )
            except ValidationError as exc:
                return _json({"error": str(exc)}, 409)

        return _json(
            {
                "uuid": receipt.uuid,
                "state": receipt.state,
                "replayed": False,
            }
        )

