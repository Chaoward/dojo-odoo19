# run alone: python3 -I tests/test_webhook_utils.py (from the bridge folder, no odoo needed)
import hashlib, hmac, sys, time
sys.path.insert(0, "..")
from whatsmax_webhook_utils import verify_signature, normalize

secret, body, now = "s3cret", b'{"data":{"text":"hi","contact_id":"c1"}}', int(time.time())
sig = hmac.new(secret.encode(), f"{now}.".encode() + body, hashlib.sha256).hexdigest()
good = f"t={now},v1={sig}"
assert verify_signature(secret, good, body)                        # valid
assert not verify_signature("wrong", good, body)                   # wrong secret
assert not verify_signature(secret, good, body + b" ")             # tampered body
assert not verify_signature(secret, f"t={now-999},v1={sig}", body) # stale
assert not verify_signature(secret, "", body)                      # missing header
assert not verify_signature(secret, "garbage", body)               # malformed
e = normalize("message.received", {"data": {"text": "hi", "contact_id": "c1"}}, body)
assert e["direction"] == "inbound" and e["contact_id"] == "c1" and e["event_id"].startswith("wm-")
print("all tests passed")
