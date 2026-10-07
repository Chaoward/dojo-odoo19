# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    gym_allow_hold = fields.Boolean(
        string="Allow Membership Hold/Pause",
        default=False,
        help="When enabled, staff can pause active memberships. Paused members cannot check in.",
    )
    gym_max_hold_days = fields.Integer(
        string="Max Hold Days (Allowance)",
        default=30,
        help="Maximum total days a membership can be paused across all hold periods.",
    )

    @api.constrains("gym_allow_hold", "gym_max_hold_days")
    def _check_gym_hold_settings(self):
        for company in self:
            if company.gym_allow_hold and company.gym_max_hold_days <= 0:
                raise ValidationError(
                    _("Max Hold Days must be greater than 0 when membership hold/pause is enabled."),
                )
