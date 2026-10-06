import os, json, time, threading, subprocess, urllib.request as U, urllib.error as X
os.environ.update(TALBISTA_DB=":memory:", ADMIN_PASSWORD="AdminPass123", ADMIN_PHONE="0910000000")
import server
from http.server import HTTPServer
calls = []; server.push_send = lambda ep, auth: calls.append((ep, auth))
server.init(); threading.Thread(target=HTTPServer(("127.0.0.1", 8767), server.H).serve_forever, daemon=True).start()


def c(m, p, b=None, t=None):
    r = U.Request("http://127.0.0.1:8767" + p, json.dumps(b or {}).encode() if m != "GET" else None, method=m,
                  headers={"Authorization": "Bearer " + str(t), "Content-Type": "application/json"})
    try: x = U.urlopen(r); return x.status, json.loads(x.read())
    except X.HTTPError as e: return e.code, json.loads(e.read())


L = lambda p, pw: c("POST", "/api/login", {"phone": p, "password": pw})[1].get("token")
A = L("0910000000", "AdminPass123")
c("POST", "/api/admin/drivers", dict(name="سائق", phone="0921111111", password="DriverPass1", car="a", model="b", year=2020, color="c", plate="1"), A)
D = L("0921111111", "DriverPass1"); c("POST", "/api/driver/available", {"available": True}, D)
c("POST", "/api/register", dict(name="عميل", phone="0931111111", password="CustPass123")); C = L("0931111111", "CustPass123")
EP = "https://fcm.googleapis.com/fcm/send/abc123"
assert c("GET", "/api/push/key", t=C)[0] == 403 and len(c("GET", "/api/push/key", t=D)[1]["key"]) == 87
assert c("POST", "/api/push/subscribe", {"endpoint": EP}, C)[0] == 403
assert c("POST", "/api/push/subscribe", {"endpoint": "https://evil.example.com/x"}, D)[0] == 400 and c("POST", "/api/push/subscribe", {"endpoint": "http://fcm.googleapis.com/x"}, D)[0] == 400
assert c("POST", "/api/push/subscribe", {"endpoint": EP}, D)[0] == 200
for urgent in (False, True):
    n = len(calls); c("POST", "/api/orders", dict(service_id=1, pickup="أ", dropoff="ب", details="x", urgent=urgent), C)
    for _ in range(30):
        if len(calls) > n: break
        time.sleep(.1)
    assert len(calls) == n + 1 and calls[-1][0] == EP and calls[-1][1].startswith("vapid t="), "push sent on new offer"
js = """const c=require('crypto');const[t,k]=process.argv.slice(1);const[h,p,s]=t.split('.');const b=Buffer.from(k,'base64url');
const pub=c.createPublicKey({key:{kty:'EC',crv:'P-256',x:b.subarray(1,33).toString('base64url'),y:b.subarray(33).toString('base64url')},format:'jwk'});
console.log(c.verify('sha256',Buffer.from(h+'.'+p),{key:pub,dsaEncoding:'ieee-p1363'},Buffer.from(s,'base64url')),JSON.parse(Buffer.from(p,'base64url')).aud)"""
for _ in range(3):
    a = server.vapid_header(EP); out = subprocess.run(["node", "-e", js, a.split("t=")[1].split(",")[0], a.split("k=")[1]], capture_output=True, text=True).stdout.split()
    assert out == ["true", "https://fcm.googleapis.com"], out
c("POST", "/api/push/unsubscribe", {"endpoint": EP}, D); n = len(calls); c("POST", "/api/orders", dict(service_id=1, pickup="أ", dropoff="ب", details="x"), C); time.sleep(.5); assert len(calls) == n
print("PUSH OK")
