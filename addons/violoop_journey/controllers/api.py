from odoo import http
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


def _serialize(record):
    version = record.active_version_id
    return {
        "id": record.id,
        "uuid": record.uuid,
        "name": record.name,
        "kind": record.kind,
        "state": record.state,
        "description": record.description or "",
        "active_version": {
            "id": version.id,
            "version": version.version,
            "state": version.state,
            "checksum": version.checksum or None,
            "nodes": [{
                "key": node.key,
                "name": node.name,
                "type": node.node_type,
                "config": node.config_json or {},
            } for node in version.node_ids],
            "edges": [{
                "source": edge.source_key,
                "target": edge.target_key,
                "label": edge.label or "",
                "condition": edge.condition_json or {},
            } for edge in version.edge_ids],
        } if version else None,
    }


class VioloopJourneyApi(http.Controller):
    @http.route(
        "/violoop/v1/journeys",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["GET"],
        csrf=False,
        save_session=False,
        readonly=True,
    )
    def list_journeys(self):
        denied = _require_api()
        if denied:
            return denied
        records = request.env["violoop.journey"].search(
            [("company_id", "in", request.env.companies.ids)],
            order="name",
            limit=100,
        )
        return _json({"items": [_serialize(record) for record in records]})

    @http.route(
        "/violoop/v1/journeys",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def create_journey(self):
        denied = _require_api()
        if denied:
            return denied

        payload = _body()
        name = str(payload.get("name") or "").strip()
        if not name:
            return _json({"error": "name is required"}, 400)

        kind = str(payload.get("kind") or "journey")
        if kind not in {"journey", "sop", "call_flow"}:
            return _json({"error": "unsupported journey kind"}, 400)

        nodes = payload.get("nodes")
        edges = payload.get("edges")
        if not isinstance(nodes, list) or not nodes:
            return _json({"error": "nodes must be a non-empty list"}, 400)
        if not isinstance(edges, list):
            return _json({"error": "edges must be a list"}, 400)

        keys = [str(n.get("key") or "") for n in nodes if isinstance(n, dict)]
        if len(keys) != len(nodes) or not all(keys) or len(keys) != len(set(keys)):
            return _json({"error": "node keys must be non-empty and unique"}, 400)

        key_set = set(keys)
        for edge in edges:
            if not isinstance(edge, dict):
                return _json({"error": "every edge must be an object"}, 400)
            if edge.get("source") not in key_set or edge.get("target") not in key_set:
                return _json({"error": "edge references an unknown node"}, 400)

        Journey = request.env["violoop.journey"]
        Version = request.env["violoop.journey.version"]
        Node = request.env["violoop.journey.node"]
        Edge = request.env["violoop.journey.edge"]

        record = Journey.create({
            "name": name[:255],
            "kind": kind,
            "description": str(payload.get("description") or "")[:10000],
            "company_id": request.env.company.id,
        })
        version = Version.create({"journey_id": record.id, "version": 1})

        valid_types = {
            "trigger", "condition", "wait", "communication", "crm", "ai",
            "approval", "handoff", "action", "end",
        }
        for index, node in enumerate(nodes):
            node_type = str(node.get("type") or "")
            if node_type not in valid_types:
                return _json({"error": f"unsupported node type: {node_type}"}, 400)
            Node.create({
                "version_id": version.id,
                "key": str(node["key"])[:120],
                "name": str(node.get("name") or node["key"])[:255],
                "node_type": node_type,
                "sequence": (index + 1) * 10,
                "config_json": node.get("config")
                    if isinstance(node.get("config"), dict) else {},
            })

        for edge in edges:
            Edge.create({
                "version_id": version.id,
                "source_key": str(edge["source"])[:120],
                "target_key": str(edge["target"])[:120],
                "label": str(edge.get("label") or "")[:255],
                "condition_json": edge.get("condition")
                    if isinstance(edge.get("condition"), dict) else {},
            })

        return _json(_serialize(record), 201)

    @http.route(
        "/violoop/v1/journeys/<string:journey_uuid>/publish",
        type="http",
        auth="bearer",
        bearer_scope="rpc",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def publish_journey(self, journey_uuid):
        denied = _require_api()
        if denied:
            return denied

        record = request.env["violoop.journey"].search([
            ("uuid", "=", journey_uuid),
            ("company_id", "in", request.env.companies.ids),
        ], limit=1)
        if not record:
            return _json({"error": "journey not found"}, 404)

        drafts = record.version_ids.filtered(lambda item: item.state == "draft")
        if not drafts:
            return _json({"error": "no draft version is available"}, 409)

        version = drafts.sorted("version", reverse=True)[:1]
        version.action_publish()
        return _json(_serialize(record))
