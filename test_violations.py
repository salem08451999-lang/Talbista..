import os, json, time, threading, urllib.request as U, urllib.error as X
os.environ.update(TALBISTA_DB=":memory:", ADMIN_PASSWORD="AdminPass123", ADMIN_PHONE="0910000000")
import server
from http.server import HTTPServer
SH = [0]; _r = time.time; server.now = lambda: int(_r()) + SH[0]   # controllable clock for the 24h test
server.init(); threading.Thread(target=HTTPServer(("127.0.0.1", 8766), server.H).serve_forever, daemon=True).start()


def c(m, p, b=None, t=None):
    r = U.Request("http://127.0.0.1:8766" + p, json.dumps(b or {}).encode() if m != "GET" else None, method=m,
                  headers={"Authorization": "Bearer " + str(t), "Content-Type": "application/json"})
    try: x = U.urlopen(r); return x.status, json.loads(x.read())
    except X.HTTPError as e: return e.code, json.loads(e.read())


L = lambda p, pw: c("POST", "/api/login", {"phone": p, "password": pw})[1].get("token")
A = L("0910000000", "AdminPass123")
did = c("POST", "/api/admin/drivers", dict(name="سائق", phone="0921111111", password="DriverPass1", car="a", model="b", year=2020, color="c", plate="1"), A)[1]["id"]
D = L("0921111111", "DriverPass1"); c("POST", "/api/driver/available", {"available": True}, D)
c("POST", "/api/register", dict(name="عميل", phone="0931111111", password="CustPass123")); C = L("0931111111", "CustPass123")
me = lambda: c("GET", "/api/me", t=D)[1]["driver"]; offers = lambda: c("GET", "/api/driver/offers", t=D)[1]
mk = lambda: c("POST", "/api/orders", dict(service_id=1, pickup="أ", dropoff="ب", details="x"), C)[1]["id"]
o = mk(); assert offers()[0]["order_id"] == o
V = f"/api/admin/drivers/{did}/violations"
assert c("POST", V, {"reason": "x"}, D)[0] == 403 and c("POST", V, {"reason": "x"}, C)[0] == 403 and c("POST", V, {}, A)[0] == 400
vid = c("POST", V, {"reason": "تجاهل الطلب بعد قبوله", "order_id": o}, A)[1]["id"]
assert me()["outstanding"] == 10 and abs(me()["blocked_until"] - (server.now() + 86400)) < 5
lg = c("GET", "/api/driver/ledger", t=D)[1][0]; assert lg["kind"] == "FINE" and lg["amount"] == 10 and lg["order_id"] == o
assert offers() == [] and c("POST", f"/api/driver/offers/{o}/accept", {}, D)[0] == 409
o2 = mk(); assert offers() == [], "blocked driver gets nothing"
dv = c("GET", "/api/driver/violations", t=D)[1][0]; assert dv["reason"].startswith("تجاهل") and dv["fine"] == 10 and dv["order_id"] == o
assert "24" in c("GET", "/api/notifications", t=D)[1][0]["text"] or any("24" in n["text"] for n in c("GET", "/api/notifications", t=D)[1])
st = c("GET", "/api/admin/stats", t=A)[1]; assert st["blocked_drivers"] == 1 and st["fines_total"] == 10
c("POST", "/api/driver/handover-request", t=D); hid = c("GET", "/api/admin/handovers", t=A)[1][0]["id"]; c("POST", f"/api/admin/handovers/{hid}/confirm", t=A)
assert me()["outstanding"] == 0 and offers() == [], "settling cash does not lift the block"
SH[0] = 86400 + 5; assert offers() and me()["blocked_until"] < server.now(), "block ends after 24h"
vs = c("GET", "/api/admin/violations", t=A)[1]; assert vs[0]["status"] == "ACTIVE" and vs[0]["fine"] == 10
assert any(l["kind"] == "FINE" for l in c("GET", "/api/admin/ledger", t=A)[1]), "fine stays in ledger"
v2 = c("POST", V, {"reason": "شكوى مؤكدة"}, A)[1]["id"]; assert me()["outstanding"] == 10 and offers() == []
assert c("POST", f"/api/admin/violations/{v2}/cancel", {"note": "x"}, D)[0] == 403
assert c("POST", f"/api/admin/violations/{v2}/cancel", {"note": "أُلغيت بعد المراجعة"}, A)[0] == 200 and me()["outstanding"] == 0 and me()["blocked_until"] < server.now()
assert c("POST", f"/api/admin/violations/{v2}/cancel", {"note": "x"}, A)[0] == 409 and offers()
kinds = [l["kind"] for l in c("GET", "/api/admin/ledger", t=A)[1]]; assert kinds.count("FINE") == 2 and kinds.count("FINE_REVERSAL") == 1
try: server.ex("delete from violations where 1=0"); server.ex("update ledger set amount=0"); assert 0
except Exception as e: assert "immutable" in str(e)
acts = [x["action"] for x in c("GET", "/api/admin/audit", t=A)[1]]; assert acts.count("create_violation") == 2 and "cancel_violation" in acts
print("VIOLATIONS OK")
