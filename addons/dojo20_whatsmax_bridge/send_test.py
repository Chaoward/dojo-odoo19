# sends a fake, signed whatsmax message to your real local odoo.
# run: python3 send_test.py   (needs: pip install requests, or it falls back to urllib)
import hashlib, hmac, json, sys, time, urllib.request, urllib.error

URL = "http://localhost:8069/dojo_whatsmax/v1/webhook"
SECRET = "demo-secret"   # must match odoo setting dojo.whatsmax.webhook_secret

# change the id each run to send a "new" message; keep it to test the duplicate check
msg_id = sys.argv[1] if len(sys.argv) > 1 else "msg_" + str(int(time.time()))
body = json.dumps({"id": msg_id, "data": {"contact_id": "maya-chen", "channel": "whatsapp",
                   "text": "Can I move my class to Friday?"}}).encode()

# sign it the way whatsmax does: hmac-sha256 of "<timestamp>.<body>"
t = int(time.time())
sig = hmac.new(SECRET.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()

req = urllib.request.Request(URL, data=body, method="POST", headers={
    "Content-Type": "application/json",
    "X-Webhook-Event": "message.received",
    "X-Webhook-Signature": f"t={t},v1={sig}",
})
try:
    r = urllib.request.urlopen(req)
    print(r.status, r.read().decode())
except urllib.error.HTTPError as e:
    print(e.code, e.read().decode())
