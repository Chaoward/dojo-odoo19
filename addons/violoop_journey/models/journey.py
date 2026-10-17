import hashlib
import json
from collections import defaultdict, deque
from uuid import uuid4

from odoo import api, fields, models
from odoo.exceptions import ValidationError


def _checksum(nodes, edges):
    encoded = json.dumps(
        {"nodes": nodes, "edges": edges},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class VioloopJourney(models.Model):
    _name = "violoop.journey"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Violoop Journey / SOP"
    _order = "name, id"
    _check_company_auto = True

    uuid = fields.Char(
        required=True,
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: str(uuid4()),
    )
    name = fields.Char(required=True, tracking=True)
    kind = fields.Selection(
        [
            ("journey", "Customer Journey"),
            ("sop", "AI / Human SOP"),
            ("call_flow", "Call Flow"),
        ],
        default="journey",
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("published", "Published"),
            ("archived", "Archived"),
        ],
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    description = fields.Text()
    version_ids = fields.One2many(
        "violoop.journey.version",
        "journey_id",
    )
    active_version_id = fields.Many2one(
        "violoop.journey.version",
        copy=False,
    )

    _uuid_unique = models.Constraint(
        "UNIQUE(uuid)",
        "Journey UUID must be unique.",
    )


class VioloopJourneyVersion(models.Model):
    _name = "violoop.journey.version"
    _description = "Violoop Journey Version"
    _order = "journey_id, version desc"
    _check_company_auto = True

    journey_id = fields.Many2one(
        "violoop.journey",
        required=True,
        ondelete="cascade",
        check_company=True,
        index=True,
    )
    company_id = fields.Many2one(
        related="journey_id.company_id",
        store=True,
        index=True,
    )
    version = fields.Integer(required=True, default=1)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("published", "Published"),
            ("archived", "Archived"),
        ],
        default="draft",
        required=True,
        index=True,
    )
    checksum = fields.Char(readonly=True, index=True)
    published_at = fields.Datetime(readonly=True)
    node_ids = fields.One2many(
        "violoop.journey.node",
        "version_id",
    )
    edge_ids = fields.One2many(
        "violoop.journey.edge",
        "version_id",
    )

    _version_unique = models.Constraint(
        "UNIQUE(journey_id, version)",
        "Journey version numbers must be unique.",
    )

    def graph_payload(self):
        self.ensure_one()
        return {
            "nodes": [
                {
                    "key": node.key,
                    "type": node.node_type,
                    "name": node.name,
                    "config": node.config_json or {},
                }
                for node in self.node_ids
            ],
            "edges": [
                {
                    "source": edge.source_key,
                    "target": edge.target_key,
                    "label": edge.label or "",
                    "condition": edge.condition_json or {},
                }
                for edge in self.edge_ids
            ],
        }

    def _validate_graph(self, graph):
        nodes = graph["nodes"]
        edges = graph["edges"]
        if not nodes:
            raise ValidationError(
                "A journey version requires at least one node."
            )

        by_key = {}
        for node in nodes:
            key = node["key"]
            if not key or key in by_key:
                raise ValidationError(
                    "Journey node keys must be non-empty and unique."
                )
            by_key[key] = node

        triggers = [
            key
            for key, node in by_key.items()
            if node["type"] == "trigger"
        ]
        if len(triggers) != 1:
            raise ValidationError(
                "A journey version must contain exactly one trigger node."
            )

        outgoing = defaultdict(list)
        indegree = {key: 0 for key in by_key}
        for edge in edges:
            source = edge["source"]
            target = edge["target"]
            if source not in by_key or target not in by_key:
                raise ValidationError(
                    "Journey edges must reference existing nodes."
                )
            outgoing[source].append(target)
            indegree[target] += 1

        roots = sorted(
            key
            for key, count in indegree.items()
            if count == 0
        )
        if roots != triggers:
            raise ValidationError(
                "The trigger must be the journey graph's only root node."
            )

        queue = deque(roots)
        visited = []
        while queue:
            key = queue.popleft()
            visited.append(key)
            for target in sorted(outgoing[key]):
                indegree[target] -= 1
                if indegree[target] == 0:
                    queue.append(target)

        if len(visited) != len(by_key):
            raise ValidationError(
                "Implicit graph cycles are not allowed."
            )

        if not any(not outgoing[key] for key in by_key):
            raise ValidationError(
                "A journey graph requires at least one terminal node."
            )

    def action_publish(self):
        for version in self:
            if version.state != "draft":
                raise ValidationError(
                    "Only draft journey versions can be published."
                )

            graph = version.graph_payload()
            version._validate_graph(graph)

            version.write(
                {
                    "state": "published",
                    "checksum": _checksum(
                        graph["nodes"],
                        graph["edges"],
                    ),
                    "published_at": fields.Datetime.now(),
                }
            )
            version.journey_id.write(
                {
                    "state": "published",
                    "active_version_id": version.id,
                }
            )

    def write(self, values):
        if any(record.state == "published" for record in self):
            forbidden = set(values) - {"state"}
            if forbidden:
                raise ValidationError(
                    "Published journey versions are immutable. "
                    "Create a new version."
                )
        return super().write(values)


class VioloopJourneyNode(models.Model):
    _name = "violoop.journey.node"
    _description = "Violoop Journey Node"
    _order = "sequence, id"

    version_id = fields.Many2one(
        "violoop.journey.version",
        required=True,
        ondelete="cascade",
        index=True,
    )
    key = fields.Char(required=True, index=True)
    name = fields.Char(required=True)
    node_type = fields.Selection(
        [
            ("trigger", "Trigger"),
            ("condition", "Condition"),
            ("wait", "Wait"),
            ("communication", "Communication"),
            ("crm", "CRM"),
            ("ai", "AI"),
            ("approval", "Approval"),
            ("handoff", "Human Handoff"),
            ("action", "Business Action"),
            ("end", "End"),
        ],
        required=True,
        index=True,
    )
    sequence = fields.Integer(default=10)
    config_json = fields.Json(default=dict)

    _node_key_unique = models.Constraint(
        "UNIQUE(version_id, key)",
        "Journey node keys must be unique within a version.",
    )

    def _ensure_draft_versions(self):
        if any(record.version_id.state != "draft" for record in self):
            raise ValidationError(
                "Only draft journey versions can be modified."
            )

    @api.model_create_multi
    def create(self, vals_list):
        version_ids = {
            int(values["version_id"])
            for values in vals_list
            if values.get("version_id")
        }
        versions = self.env["violoop.journey.version"].browse(
            version_ids
        )
        if any(version.state != "draft" for version in versions):
            raise ValidationError(
                "Nodes can only be added to draft journey versions."
            )
        return super().create(vals_list)

    def write(self, values):
        self._ensure_draft_versions()
        return super().write(values)

    def unlink(self):
        self._ensure_draft_versions()
        return super().unlink()


class VioloopJourneyEdge(models.Model):
    _name = "violoop.journey.edge"
    _description = "Violoop Journey Edge"
    _order = "id"

    version_id = fields.Many2one(
        "violoop.journey.version",
        required=True,
        ondelete="cascade",
        index=True,
    )
    source_key = fields.Char(required=True)
    target_key = fields.Char(required=True)
    label = fields.Char()
    condition_json = fields.Json(default=dict)

    def _ensure_draft_versions(self):
        if any(record.version_id.state != "draft" for record in self):
            raise ValidationError(
                "Only draft journey versions can be modified."
            )

    @api.model_create_multi
    def create(self, vals_list):
        version_ids = {
            int(values["version_id"])
            for values in vals_list
            if values.get("version_id")
        }
        versions = self.env["violoop.journey.version"].browse(
            version_ids
        )
        if any(version.state != "draft" for version in versions):
            raise ValidationError(
                "Edges can only be added to draft journey versions."
            )
        return super().create(vals_list)

    def write(self, values):
        self._ensure_draft_versions()
        return super().write(values)

    def unlink(self):
        self._ensure_draft_versions()
        return super().unlink()


class VioloopJourneyEnrollment(models.Model):
    _name = "violoop.journey.enrollment"
    _description = "Violoop Journey Enrollment"
    _order = "create_date desc, id desc"
    _check_company_auto = True

    uuid = fields.Char(
        required=True,
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: str(uuid4()),
    )
    external_event_id = fields.Char(copy=False, index=True)
    version_id = fields.Many2one(
        "violoop.journey.version",
        required=True,
        ondelete="restrict",
        check_company=True,
        index=True,
    )
    company_id = fields.Many2one(
        related="version_id.company_id",
        store=True,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        check_company=True,
        index=True,
    )
    conversation_id = fields.Many2one(
        "violoop.conversation",
        check_company=True,
        index=True,
    )
    state = fields.Selection(
        [
            ("active", "Active"),
            ("waiting", "Waiting"),
            ("approval", "Approval"),
            ("human", "Human Handoff"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
            ("failed", "Failed"),
        ],
        default="active",
        required=True,
        index=True,
    )
    current_node_key = fields.Char(index=True)
    next_run_at = fields.Datetime(index=True)
    context_json = fields.Json(default=dict)
    execution_ids = fields.One2many(
        "violoop.journey.execution",
        "enrollment_id",
    )

    _uuid_unique = models.Constraint(
        "UNIQUE(uuid)",
        "Journey enrollment UUID must be unique.",
    )
    _external_event_unique = models.Constraint(
        "UNIQUE(external_event_id)",
        "Journey enrollment external event ID must be unique.",
    )


class VioloopJourneyExecution(models.Model):
    _name = "violoop.journey.execution"
    _description = "Violoop Journey Node Execution"
    _order = "started_at desc, id desc"
    _check_company_auto = True

    uuid = fields.Char(
        required=True,
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: str(uuid4()),
    )
    enrollment_id = fields.Many2one(
        "violoop.journey.enrollment",
        required=True,
        ondelete="cascade",
        check_company=True,
        index=True,
    )
    company_id = fields.Many2one(
        related="enrollment_id.company_id",
        store=True,
        index=True,
    )
    node_key = fields.Char(required=True, index=True)
    state = fields.Selection(
        [
            ("running", "Running"),
            ("waiting", "Waiting"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("skipped", "Skipped"),
        ],
        default="running",
        required=True,
        index=True,
    )
    input_json = fields.Json(default=dict)
    output_json = fields.Json(default=dict)
    error_message = fields.Text()
    started_at = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
    )
    ended_at = fields.Datetime()

    _uuid_unique = models.Constraint(
        "UNIQUE(uuid)",
        "Journey execution UUID must be unique.",
    )
