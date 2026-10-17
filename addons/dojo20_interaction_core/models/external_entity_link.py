from odoo import api, fields, models


class DojoExternalEntityLink(models.Model):
    _name = "dojo.external.entity.link"
    _description = "Dojang External Entity Link"
    _order = "write_date desc, id desc"

    active = fields.Boolean(default=True, index=True)
    provider = fields.Selection(
        [
            ("whatsmax", "WhatsMax"),
            ("odoo_legacy", "Legacy Odoo"),
            ("telnyx", "Telnyx"),
            ("agentphone", "AgentPhone"),
            ("agentmail", "AgentMail"),
            ("livekit", "LiveKit"),
            ("google", "Google"),
            ("other", "Other")
        ],
        required=True,
        index=True
    )
    external_type = fields.Char(required=True, index=True)
    external_id = fields.Char(required=True, index=True)
    res_model = fields.Char(required=True, index=True)
    res_id = fields.Integer(required=True, index=True)
    partner_id = fields.Many2one("res.partner", ondelete="cascade", index=True)
    workspace_key = fields.Char(index=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        ondelete="cascade",
        index=True
    )
    metadata = fields.Json(default=dict)

    _provider_identity_unique = models.Constraint(
        "unique(company_id, provider, external_type, external_id)",
        "An external provider identity can only map once inside a company."
    )

    @api.model
    def resolve(self, provider, external_type, external_id, company=None):
        company = company or self.env.company
        return self.search(
            [
                ("company_id", "=", company.id),
                ("provider", "=", provider),
                ("external_type", "=", external_type),
                ("external_id", "=", str(external_id)),
                ("active", "=", True)
            ],
            limit=1
        )
