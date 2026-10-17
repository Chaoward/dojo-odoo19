from odoo import fields, models


class VioloopFacilitySite(models.Model):
    _name = "violoop.facility.site"
    _description = "Violoop Facility Site"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(required=True, index=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    timezone = fields.Char(default="UTC")
    latitude = fields.Float(digits=(10, 7))
    longitude = fields.Float(digits=(10, 7))
    altitude_m = fields.Float()
    niantic_site_id = fields.Char(index=True)
    niantic_anchor_payload = fields.Text()
    edge_node_ids = fields.One2many("violoop.edge.node", "site_id")
    spatial_anchor_ids = fields.One2many("violoop.spatial.anchor", "site_id")
    metadata_json = fields.Json(default=dict)

    _code_company_unique = models.Constraint(
        "UNIQUE(code, company_id)",
        "Facility site code must be unique per company.",
    )


class VioloopEdgeNode(models.Model):
    _name = "violoop.edge.node"
    _description = "Violoop Edge Node"
    _inherit = ["mail.thread"]
    _order = "name"
    _check_company_auto = True

    name = fields.Char(required=True)
    node_uid = fields.Char(required=True, index=True, copy=False)
    site_id = fields.Many2one(
        "violoop.facility.site",
        ondelete="set null",
        check_company=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="site_id.company_id",
        store=True,
        index=True,
    )
    status = fields.Selection(
        [("online", "Online"), ("degraded", "Degraded"), ("offline", "Offline")],
        default="offline",
        required=True,
        tracking=True,
    )
    last_seen_at = fields.Datetime(index=True, tracking=True)
    software_version = fields.Char()
    capabilities_json = fields.Json(default=dict)

    _node_uid_unique = models.Constraint(
        "UNIQUE(node_uid)",
        "Edge node UID must be globally unique in this tenant database.",
    )


class VioloopSpatialAnchor(models.Model):
    _name = "violoop.spatial.anchor"
    _description = "Violoop Spatial Anchor"
    _order = "create_date desc"
    _check_company_auto = True

    anchor_uid = fields.Char(required=True, index=True, copy=False)
    name = fields.Char(required=True)
    site_id = fields.Many2one(
        "violoop.facility.site",
        required=True,
        ondelete="cascade",
        check_company=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="site_id.company_id",
        store=True,
        index=True,
    )
    maintenance_request_id = fields.Many2one(
        "maintenance.request",
        ondelete="cascade",
        check_company=True,
        index=True,
    )
    nsdk_site_id = fields.Char(index=True)
    site_anchor_payload = fields.Text()
    reference_frame = fields.Selection(
        [("vps2_site_anchor", "VPS2 Site Anchor")],
        default="vps2_site_anchor",
        required=True,
    )
    position_x = fields.Float(required=True)
    position_y = fields.Float(required=True)
    position_z = fields.Float(required=True)
    rotation_x = fields.Float(required=True)
    rotation_y = fields.Float(required=True)
    rotation_z = fields.Float(required=True)
    rotation_w = fields.Float(required=True, default=1.0)
    source_device_uid = fields.Char(index=True)
    captured_at = fields.Datetime(default=fields.Datetime.now, required=True)
    metadata_json = fields.Json(default=dict)

    _anchor_uid_unique = models.Constraint(
        "UNIQUE(anchor_uid)",
        "Spatial anchor UID must be unique.",
    )
