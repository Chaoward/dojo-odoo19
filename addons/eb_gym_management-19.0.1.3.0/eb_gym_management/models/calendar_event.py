# -*- coding: utf-8 -*-
from odoo import fields, models


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    membership_id = fields.Many2one(
        "gym.membership",
        string="Membership",
        help="Links this class booking to a member's membership.",
    )
