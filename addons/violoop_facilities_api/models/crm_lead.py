from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    violoop_external_event_id = fields.Char(
        index=True,
        copy=False,
    )
    violoop_source = fields.Selection(
        [
            ("odoo", "Odoo"),
            ("console", "Console"),
            ("kiosk", "Kiosk"),
            ("ai_assist", "AI Assist"),
            ("edge", "Edge"),
        ],
        default="odoo",
        required=True,
        index=True,
    )
    violoop_ai_summary = fields.Text()
    violoop_last_ai_touch_at = fields.Datetime(index=True)

    _violoop_external_event_unique = models.Constraint(
        "UNIQUE(violoop_external_event_id)",
        "CRM event ID must be unique.",
    )
