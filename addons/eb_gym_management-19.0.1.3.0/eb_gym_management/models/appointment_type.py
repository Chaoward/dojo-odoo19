# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AppointmentType(models.Model):
    _inherit = "appointment.type"

    is_gym_class = fields.Boolean(string="Is Gym Class", default=False)
    class_category = fields.Selection(
        [
            ("yoga", "Yoga"),
            ("zumba", "Zumba"),
            ("hiit", "HIIT"),
            ("pilates", "Pilates"),
            ("spinning", "Spinning"),
            ("other", "Other"),
        ],
        string="Class Category",
    )

    @api.onchange("is_gym_class")
    def _onchange_is_gym_class(self):
        if not self.is_gym_class:
            self.class_category = False
