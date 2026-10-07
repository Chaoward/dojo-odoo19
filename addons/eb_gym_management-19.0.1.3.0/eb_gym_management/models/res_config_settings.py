# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    gym_allow_hold = fields.Boolean(
        string="Allow Membership Hold/Pause",
        related="company_id.gym_allow_hold",
        readonly=False,
    )
    gym_max_hold_days = fields.Integer(
        string="Max Hold Days (Allowance)",
        related="company_id.gym_max_hold_days",
        readonly=False,
    )
