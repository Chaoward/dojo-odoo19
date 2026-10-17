from odoo import fields, models


class MaintenanceRequest(models.Model):
    _inherit = "maintenance.request"

    facility_site_id = fields.Many2one(
        "violoop.facility.site",
        ondelete="set null",
        check_company=True,
        index=True,
        tracking=True,
    )
    external_event_id = fields.Char(index=True, copy=False)
    source = fields.Selection(
        [
            ("odoo", "Odoo"),
            ("kiosk", "Kiosk"),
            ("trace", "Trace"),
            ("mobile", "Mobile"),
            ("spatial", "Spatial"),
            ("edge", "Edge"),
            ("ai_assist", "AI Assist"),
        ],
        default="odoo",
        required=True,
        tracking=True,
    )
    capture_reference = fields.Char(index=True)
    ai_summary = fields.Text()
    ai_risk = fields.Selection(
        [
            ("none", "None"),
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
            ("critical", "Critical"),
        ],
        default="none",
        tracking=True,
    )
    spatial_anchor_ids = fields.One2many(
        "violoop.spatial.anchor",
        "maintenance_request_id",
        string="Spatial Anchors",
    )

    _external_event_unique = models.Constraint(
        "UNIQUE(external_event_id)",
        "Maintenance event ID must be unique.",
    )
