# pure helpers for the whatsmax webhook. no odoo imports, so they can be tested alone.
import hashlib
import hmac
import time

TOLERANCE = 300  # seconds a signature stays valid (blocks replayed requests)

# whatsmax events we turn into odoo interaction events. everything else is acknowledged and ignored
HANDLED_EVENTS = {"message.received"}


def verify_signature(secret, header, raw_body, now=None):
    # 1. header looks like "t=1759240000,v1=6f1c..."
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        timestamp = int(parts["t"])
        signature = parts["v1"]
    except (KeyError, ValueError, AttributeError):
        return False
    # 2. reject old timestamps so a captured request cannot be replayed later
    if abs((now or time.time()) - timestamp) > TOLERANCE:
        return False
    # 3. whatsmax signs "<t>.<raw body>" with hmac-sha256
    expected = hmac.new(
        secret.encode("utf-8"),
        str(timestamp).encode("utf-8") + b"." + raw_body,
        hashlib.sha256,
    ).hexdigest()
    # 4. constant-time compare so timing cannot leak the signature
    return hmac.compare_digest(expected, signature)


def normalize(event_name, payload, raw_body):
    # 1. real whatsmax shape: {event, timestamp, message: {id, conversation_id, direction, channel, body, sent_at}}
    data = payload.get("message") or payload.get("data") or payload
    # 2. event id: the message id is stable across retries. (hashing the whole body would not be,
    #    because the body carries a fresh timestamp on every delivery attempt)
    message_id = data.get("id") or data.get("message_id")
    event_id = f"msg-{message_id}" if message_id else "wm-" + hashlib.sha256(raw_body).hexdigest()[:32]
    # 3. whatsmax calls the text "body"
    text = data.get("body") or data.get("text") or ""
    # 4. the shape ingest_normalized_event() already expects.
    #    contact_id is absent from the real payload, so the partner link stays empty for now
    return {
        "event_id": str(event_id),
        "contact_id": data.get("contact_id"),
        "conversation_id": data.get("conversation_id"),
        "kind": "message",
        "direction": data.get("direction") or ("inbound" if event_name == "message.received" else "outbound"),
        "channel": data.get("channel"),
        "text": text,
        "summary": text[:120] or event_name,
        "occurred_at": data.get("sent_at"),
    }
