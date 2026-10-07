# -*- coding: utf-8 -*-
from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError

GYM_ADMIN_XMLID = "eb_gym_management.group_gym_manager"
GYM_RECEPTION_XMLID = "eb_gym_management.group_gym_reception"
GYM_TRAINER_XMLID = "eb_gym_management.group_gym_trainer"
GYM_NUTRITIONIST_XMLID = "eb_gym_management.group_gym_nutritionist"
GYM_BRANCH_MANAGER_XMLID = "eb_gym_management.group_gym_branch_manager"

# Field name -> group xmlid. The gym role groups have
# no privilege_id/category (see gym_security.xml), so several can be granted
# to the same user at once instead of being forced into Odoo's one-choice-
# per-privilege dropdown - but that also means the web client only shows them
# under Access Rights > Extra Rights in Developer Mode (res_user_group_ids_field.js
# gates that section behind odoo.debug). These writable mirror fields back a
# permanently visible "Gym Roles" section on the user form (res_users_views.xml)
# so roles can be granted without needing developer mode.
GYM_ROLE_FIELDS = {
    "is_gym_receptionist": GYM_RECEPTION_XMLID,
    "is_gym_trainer": GYM_TRAINER_XMLID,
    "is_gym_nutritionist": GYM_NUTRITIONIST_XMLID,
    "is_gym_branch_manager": GYM_BRANCH_MANAGER_XMLID,
    "is_gym_administrator": GYM_ADMIN_XMLID,
}


class ResUsers(models.Model):
    _inherit = "res.users"

    is_gym_receptionist = fields.Boolean(
        string="Gym Receptionist",
        compute="_compute_gym_role_flags",
        inverse="_inverse_is_gym_receptionist",
    )
    is_gym_trainer = fields.Boolean(
        string="Gym Trainer",
        compute="_compute_gym_role_flags",
        inverse="_inverse_is_gym_trainer",
    )
    is_gym_nutritionist = fields.Boolean(
        string="Gym Nutritionist",
        compute="_compute_gym_role_flags",
        inverse="_inverse_is_gym_nutritionist",
    )
    is_gym_branch_manager = fields.Boolean(
        string="Gym Branch Manager",
        compute="_compute_gym_role_flags",
        inverse="_inverse_is_gym_branch_manager",
    )
    is_gym_administrator = fields.Boolean(
        string="Gym Administrator",
        compute="_compute_gym_role_flags",
        inverse="_inverse_is_gym_administrator",
    )

    @api.depends("group_ids")
    def _compute_gym_role_flags(self):
        role_groups = {
            field_name: self.env.ref(xmlid, raise_if_not_found=False) for field_name, xmlid in GYM_ROLE_FIELDS.items()
        }
        for user in self:
            for field_name, group in role_groups.items():
                user[field_name] = bool(group) and group in user.all_group_ids

    def _toggle_gym_group(self, xmlid):
        """Add or remove a single gym group based on the matching field value."""
        group = self.env.ref(xmlid, raise_if_not_found=False)
        if not group:
            return
        field_name = next(k for k, v in GYM_ROLE_FIELDS.items() if v == xmlid)
        for user in self:
            if user[field_name]:
                user.group_ids = [Command.link(group.id)]
            else:
                user.group_ids = [Command.unlink(group.id)]

    def _inverse_is_gym_receptionist(self):
        self._toggle_gym_group(GYM_RECEPTION_XMLID)

    def _inverse_is_gym_trainer(self):
        self._toggle_gym_group(GYM_TRAINER_XMLID)

    def _inverse_is_gym_nutritionist(self):
        self._toggle_gym_group(GYM_NUTRITIONIST_XMLID)

    def _inverse_is_gym_branch_manager(self):
        self._toggle_gym_group(GYM_BRANCH_MANAGER_XMLID)

    def _inverse_is_gym_administrator(self):
        self._toggle_gym_group(GYM_ADMIN_XMLID)

    @api.constrains("group_ids")
    def _check_gym_admin_exclusive(self):
        """Gym Administrator already implies Receptionist/Trainer/Nutritionist
        (see gym_security.xml), so explicitly granting any of them on top of
        Administrator is never meaningful - block it instead of leaving a
        confusing, redundant access state.
        """
        admin_group = self.env.ref(GYM_ADMIN_XMLID, raise_if_not_found=False)
        if not admin_group:
            return
        role_groups = self.env["res.groups"]
        for xmlid in (GYM_RECEPTION_XMLID, GYM_TRAINER_XMLID, GYM_NUTRITIONIST_XMLID):
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                role_groups |= group
        for user in self:
            if admin_group not in user.group_ids:
                continue
            conflicting = user.group_ids & role_groups
            if conflicting:
                raise ValidationError(
                    _(
                        "%(user)s is set as Gym Administrator, which already includes "
                        "Receptionist, Trainer and Nutritionist access. Uncheck %(roles)s "
                        "or uncheck Gym Administrator.",
                        user=user.name,
                        roles=", ".join(g.name for g in conflicting),
                    ),
                )
