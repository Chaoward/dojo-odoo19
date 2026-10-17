from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from odoo import api, fields, models
from odoo.exceptions import ValidationError


BASELINE_GROUP_CAPABILITIES = {
    "violoop_facilities_api.group_violoop_facility_user": {
        "dashboard.read.site",
        "facilities.read.site",
        "maintenance.read.site",
        "locations.read.site",
    },
    "violoop_facilities_api.group_violoop_facility_manager": {
        "dashboard.read.site",
        "facilities.read.site",
        "facilities.update.site",
        "maintenance.read.site",
        "maintenance.update.site",
        "locations.read.site",
    },
    "violoop_conversation.group_violoop_conversation_user": {
        "dashboard.read.site",
        "comms.read.site",
        "crm.read.site",
        "members.read.site",
        "attendance.read.site",
        "ai.use.site",
    },
    "violoop_conversation.group_violoop_conversation_manager": {
        "dashboard.read.site",
        "comms.read.site",
        "comms.create.site",
        "comms.approve.site",
        "crm.read.site",
        "crm.update.site",
        "crm.approve.site",
        "members.read.site",
        "attendance.read.site",
        "ai.use.site",
    },
    "violoop_journey.group_violoop_journey_user": {
        "dashboard.read.site",
        "marketing.read.site",
    },
    "violoop_journey.group_violoop_journey_manager": {
        "dashboard.read.site",
        "marketing.read.site",
        "marketing.update.site",
        "marketing.approve.site",
    },
}


def _utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class VioloopCapabilityGrant(models.Model):
    _name = "violoop.capability.grant"
    _description = "Violoop Operator Capability Grant"
    _order = "user_id, capability, id"
    _check_company_auto = True

    uuid = fields.Char(
        required=True,
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: str(uuid4()),
    )
    user_id = fields.Many2one(
        "res.users",
        required=True,
        ondelete="cascade",
        index=True,
        check_company=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    facility_site_id = fields.Many2one(
        "violoop.facility.site",
        string="Facility",
        check_company=True,
        index=True,
    )
    capability = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True, index=True)
    expires_at = fields.Datetime(index=True)
    note = fields.Char()

    _uuid_unique = models.Constraint(
        "UNIQUE(uuid)",
        "Capability grant UUID must be unique.",
    )
    _grant_unique = models.Constraint(
        "UNIQUE(user_id, company_id, facility_site_id, capability)",
        "This capability grant already exists for the selected scope.",
    )

    @api.constrains("capability")
    def _check_capability_format(self):
        allowed_scopes = {"own", "site", "org"}
        for record in self:
            parts = (record.capability or "").split(".")
            if len(parts) != 3 or not all(parts):
                raise ValidationError(
                    "Capabilities must use module.action.scope format."
                )
            if parts[2] not in allowed_scopes:
                raise ValidationError(
                    "Capability scope must be own, site, or org."
                )


class VioloopOperatorSession(models.Model):
    _name = "violoop.operator.session"
    _description = "Violoop Operator Session"
    _order = "created_at desc, id desc"
    _check_company_auto = True

    uuid = fields.Char(
        required=True,
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: str(uuid4()),
    )
    jti_hash = fields.Char(required=True, index=True, copy=False)
    user_id = fields.Many2one(
        "res.users",
        required=True,
        ondelete="cascade",
        index=True,
        check_company=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        index=True,
    )
    created_at = fields.Datetime(
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    last_seen_at = fields.Datetime(index=True)
    expires_at = fields.Datetime(required=True, index=True)
    revoked_at = fields.Datetime(index=True)
    user_agent_label = fields.Char()
    source = fields.Selection(
        [
            ("control_web", "Control Web"),
            ("desktop", "Desktop"),
            ("mobile", "Mobile"),
        ],
        default="control_web",
        required=True,
    )

    _uuid_unique = models.Constraint(
        "UNIQUE(uuid)",
        "Operator session UUID must be unique.",
    )
    _jti_unique = models.Constraint(
        "UNIQUE(jti_hash)",
        "Operator session token identifier must be unique.",
    )

    def is_active_now(self):
        self.ensure_one()
        now = _utcnow_naive()
        return (
            not self.revoked_at
            and bool(self.expires_at)
            and self.expires_at > now
            and self.user_id.active
            and not self.user_id.share
        )


class ResUsers(models.Model):
    _inherit = "res.users"

    violoop_telnyx_credential_id = fields.Char(
        string="Violoop Telnyx Credential ID",
        groups="base.group_system",
        copy=False,
    )
    violoop_capability_grant_ids = fields.One2many(
        "violoop.capability.grant",
        "user_id",
        string="Violoop Capability Grants",
    )

    def _violoop_baseline_capabilities(self):
        self.ensure_one()
        capabilities = set()
        for xmlid, grants in BASELINE_GROUP_CAPABILITIES.items():
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group and group in self.group_ids:
                capabilities.update(grants)
        return capabilities

    def _violoop_explicit_capabilities(
        self,
        *,
        company_id: int,
        facility_site_id: int | None = None,
    ):
        self.ensure_one()
        now = fields.Datetime.now()
        domain = [
            ("user_id", "=", self.id),
            ("company_id", "=", company_id),
            ("active", "=", True),
            "|",
            ("expires_at", "=", False),
            ("expires_at", ">", now),
        ]
        grants = self.env["violoop.capability.grant"].search(domain)
        capabilities = set()
        for grant in grants:
            if grant.facility_site_id:
                if facility_site_id and grant.facility_site_id.id == facility_site_id:
                    capabilities.add(grant.capability)
            else:
                capabilities.add(grant.capability)
        return capabilities

    def violoop_profile(
        self,
        *,
        company_id: int | None = None,
        facility_site_id: int | None = None,
        include_private: bool = False,
    ):
        self.ensure_one()

        if not self.active or self.share or not self.has_group("base.group_user"):
            raise ValidationError(
                "Violoop operator sessions require an active internal Odoo user."
            )

        allowed_companies = self.company_ids
        selected_company = (
            self.env["res.company"].browse(company_id).exists()
            if company_id
            else self.company_id
        )
        if not selected_company or selected_company not in allowed_companies:
            raise ValidationError(
                "The selected company is not available to this operator."
            )

        capabilities = self._violoop_baseline_capabilities()
        capabilities.update(
            self._violoop_explicit_capabilities(
                company_id=selected_company.id,
                facility_site_id=facility_site_id,
            )
        )

        facilities = self.env["violoop.facility.site"].search(
            [("company_id", "=", selected_company.id)]
        )

        profile = {
            "user_id": self.id,
            "name": self.name,
            "login": self.login,
            "company_id": selected_company.id,
            "company_name": selected_company.display_name,
            "company_ids": allowed_companies.ids,
            "facility_site_ids": facilities.ids,
            "capabilities": sorted(capabilities),
            "phone_enabled": bool(self.sudo().violoop_telnyx_credential_id),
        }
        if include_private:
            profile["telnyx_credential_id"] = (
                self.sudo().violoop_telnyx_credential_id or None
            )
            profile["stripe_connected_account_id"] = (
                selected_company.sudo().violoop_stripe_connected_account_id or None
            )
        return profile



class ResCompany(models.Model):
    _inherit = "res.company"

    violoop_stripe_connected_account_id = fields.Char(
        string="Stripe Connected Account ID",
        groups="violoop_identity.group_violoop_identity_manager",
        copy=False,
    )
