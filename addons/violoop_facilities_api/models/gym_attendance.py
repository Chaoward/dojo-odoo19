from odoo import fields, models


class GymAttendance(models.Model):
    _inherit = "gym.attendance"

    external_event_id = fields.Char(index=True, copy=False)
    checkout_event_id = fields.Char(index=True, copy=False)
    facility_site_id = fields.Many2one(
        "violoop.facility.site",
        ondelete="set null",
        check_company=True,
        index=True,
    )
    source = fields.Selection(
        [("odoo", "Odoo"), ("kiosk", "Kiosk"), ("mobile", "Mobile"), ("edge", "Edge")],
        default="odoo",
        required=True,
    )

    _external_event_unique = models.Constraint(
        "UNIQUE(external_event_id)",
        "Check-in event ID must be unique.",
    )
    _checkout_event_unique = models.Constraint(
        "UNIQUE(checkout_event_id)",
        "Check-out event ID must be unique.",
    )
