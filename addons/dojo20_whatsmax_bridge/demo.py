# demo: pretends to be whatsmax sending messages to odoo, so you can watch the webhook logic work.
# run it: python3 demo.py   (no odoo, no install needed)
import hashlib, hmac, json, time
from whatsmax_webhook_utils import verify_signature, normalize, HANDLED_EVENTS

SECRET = "demo-secret"   # in real life: odoo setting dojo.whatsmax.webhook_secret
timeline = {}            # stand-in for odoo's "interaction event" table

def whatsmax_sends(event_name, body_dict, secret=SECRET):
    # this part plays whatsmax: sign the body, build the headers
    raw = json.dumps(body_dict).encode()
    t = int(time.time())
    sig = hmac.new(secret.encode(), f"{t}.".encode() + raw, hashlib.sha256).hexdigest()
    return event_name, f"t={t},v1={sig}", raw

def odoo_receives(event_name, header, raw):
    # this part plays our odoo webhook (same steps as controllers/webhook.py)
    if not verify_signature(SECRET, header, raw):
        return "401 rejected: bad signature"
    if event_name not in HANDLED_EVENTS:
        return "200 ignored: event we do not use"
    event = normalize(event_name, json.loads(raw), raw)
    if event["event_id"] in timeline:
        return "200 duplicate: already saved, skipped"
    timeline[event["event_id"]] = event
    return f'201 saved: "{event["text"]}" from contact {event["contact_id"]}'

msg = {"id": "msg_1", "data": {"contact_id": "maya-chen", "channel": "whatsapp", "text": "Can I move my class to Friday?"}}

print("1. normal message          ->", odoo_receives(*whatsmax_sends("message.received", msg)))
print("2. same message again      ->", odoo_receives(*whatsmax_sends("message.received", msg)), "(whatsmax retry)")
print("3. hacker, wrong secret    ->", odoo_receives(*whatsmax_sends("message.received", msg, secret="guess")))
print("4. event we do not handle  ->", odoo_receives(*whatsmax_sends("contact.created", msg)))
e, h, raw = whatsmax_sends("message.received", msg)
print("5. body edited in transit  ->", odoo_receives(e, h, raw.replace(b"Friday", b"NEVER")))
print("\nodoo timeline now holds", len(timeline), "event(s):", [v["text"] for v in timeline.values()])
