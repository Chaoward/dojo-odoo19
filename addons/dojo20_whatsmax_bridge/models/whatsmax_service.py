import requests

from odoo import api, models
from odoo.exceptions import UserError


class DojoWhatsMaxService(models.AbstractModel):
    _name = "dojo.whatsmax.service"
    _description = "WhatsMax Service"

    def _config(self):
        params = self.env["ir.config_parameter"].sudo()
        base_url = (params.get_str("dojo.whatsmax.base_url") or "").rstrip("/")
        token = params.get_str("dojo.whatsmax.api_token")
        if not base_url or not token:
            raise UserError("WhatsMax is not configured.")
        return base_url, token

    def _request(self, method, path, **kwargs):
        base_url, token = self._config()
        response = requests.request(
            method,
            f"{base_url}{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            timeout=15,
            **kwargs
        )
        if response.status_code >= 400:
            raise UserError(f"WhatsMax returned HTTP {response.status_code}.")
        return response.json() if response.content else {}

    @api.model
    def list_conversations(self):
        return self._request("GET", "/api/v1/conversations")

    @api.model
    def send_message(self, channel, recipient, text):
        return self._request(
            "POST",
            "/api/v1/messages/send",
            json={
                "channel": channel,
                "to": recipient,
                "text": text
            }
        )

    @api.model
    def ingest_normalized_event(self, event):
        external_contact_id = str(event.get("contact_id") or "")
        partner = False
        if external_contact_id:
            link = self.env["dojo.external.entity.link"].resolve(
                "whatsmax",
                "contact",
                external_contact_id
            )
            partner = link.partner_id if link else False

        values = {
            "source": "whatsmax",
            "source_id": str(event["event_id"]),
            "source_thread_id": str(event.get("conversation_id") or ""),
            "kind": event.get("kind", "message"),
            "direction": event.get("direction", "inbound"),
            "channel": event.get("channel"),
            "partner_id": partner.id if partner else False,
            "classification": event.get("classification", "internal"),
            "attention_state": event.get(
                "attention_state",
                "needs_reply" if event.get("direction") == "inbound" else "waiting_external"
            ),
            "summary": event.get("summary"),
            "body_text": event.get("text"),
            "payload": event
        }
        return self.env["dojo.interaction.event"].ingest(values)
