import json

from odoo import http
from odoo.http import request

from ..whatsmax_webhook_utils import HANDLED_EVENTS, normalize, verify_signature


class WhatsMaxWebhook(http.Controller):
    @http.route(
        "/dojo_whatsmax/v1/webhook",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    def receive(self):
        # 1. read the signing secret (set it in odoo: dojo.whatsmax.webhook_secret)
        params = request.env["ir.config_parameter"].sudo()
        secret = params.get_str("dojo.whatsmax.webhook_secret")
        raw = request.httprequest.get_data(cache=True) or b""
        header = request.httprequest.headers.get("X-Webhook-Signature", "")

        # 2. no secret or bad signature: reject before touching any data
        if not secret or not verify_signature(secret, header, raw):
            return request.make_json_response({"error": "unauthorized"}, status=401)

        # 3. ack events we do not use, so whatsmax does not keep retrying them
        name = request.httprequest.headers.get("X-Webhook-Event", "")
        if name not in HANDLED_EVENTS:
            return request.make_json_response({"status": "ignored"}, status=200)

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return request.make_json_response({"error": "invalid_json"}, status=400)

        # 4. reshape into odoo's format
        event = normalize(name, payload, raw)

        # 5. whatsmax retries failed deliveries. skip ones we already stored
        #    (the table has a unique constraint, so a duplicate would crash with a 500)
        seen = request.env["dojo.interaction.event"].sudo().search_count(
            [("source", "=", "whatsmax"), ("source_id", "=", event["event_id"])]
        )
        if seen:
            return request.make_json_response({"status": "duplicate"}, status=200)

        # 6. a webhook has no logged-in user, so odoo does not know the company.
        #    use the main company (the first one) for this single-company setup
        company = request.env["res.company"].sudo().search([], limit=1)

        # 7. store it. the existing method links the contact to a partner
        service = request.env["dojo.whatsmax.service"].sudo().with_context(allowed_company_ids=[company.id])
        service.ingest_normalized_event(event)
        return request.make_json_response({"status": "ok"}, status=201)
