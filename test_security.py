import json, os, http.client, urllib.request as U, urllib.error as X
H = os.path.dirname(os.path.abspath(__file__))


def c(m, p, b=None, t=None):
    r = U.Request("http://127.0.0.1:8000" + p, json.dumps(b or {}).encode() if m != "GET" else None, method=m,
                  headers={"Authorization": "Bearer " + str(t), "Content-Type": "application/json"})
    try: x = U.urlopen(r); return x.status, json.loads(x.read())
    except X.HTTPError as e: return e.code, json.loads(e.read())


L = lambda p, pw: c("POST", "/api/login", {"phone": p, "password": pw})[1].get("token")
for f in ("server.py", "index.html", "driver.html", "admin.html", "map.js"):  # no continuous tracking (position is read once at a time)
    t = open(os.path.join(H, f), encoding="utf-8").read().lower(); assert "watchposition" not in t and "watchposition" not in t, f
k = http.client.HTTPConnection("127.0.0.1", 8000); k.request("GET", "/healthz"); r = k.getresponse(); r.read(); assert r.status == 200
k.request("GET", "/"); r = k.getresponse(); r.read()
assert r.getheader("X-Frame-Options") == "DENY" and "default-src" in r.getheader("Content-Security-Policy") and r.getheader("X-Content-Type-Options") == "nosniff"
k = http.client.HTTPConnection("127.0.0.1", 8000); k.request("POST", "/api/login", headers={"Content-Length": "200000"}); assert k.getresponse().status == 413
A = L("0910000000", "AdminPass123")
assert c("POST", "/api/register", dict(name="س", phone="0931111111", password="CustPass123"))[0] == 200
assert c("POST", "/api/register", dict(name="س", phone="0931111111", password="CustPass123"))[0] == 409
assert c("POST", "/api/register", dict(name="س", phone="abc", password="CustPass123"))[0] == 400
C = L("0931111111", "CustPass123"); C2 = L("0931111111", "CustPass123")
assert c("PATCH", "/api/me", {"name": "اسم جديد"}, C)[0] == 200 and c("GET", "/api/me", t=C)[1]["name"] == "اسم جديد"
assert c("PATCH", "/api/me", {"old_password": "x", "new_password": "NewPass1234"}, C)[0] == 400
assert c("PATCH", "/api/me", {"old_password": "CustPass123", "new_password": "NewPass1234"}, C)[0] == 200
assert c("GET", "/api/me", t=C2)[0] == 401 and c("GET", "/api/me", t=C)[0] == 200
C = L("0931111111", "NewPass1234"); assert C
C3 = L("0931111111", "NewPass1234"); assert c("POST", "/api/logout", t=C3)[0] == 200 and c("GET", "/api/me", t=C3)[0] == 401
o = c("POST", "/api/orders", dict(service_id=1, pickup="أ", dropoff="ب", details="x"), C)[1]["id"]
assert sum(1 for n in c("GET", "/api/notifications", t=C)[1] if not n["read"]) > 0
c("POST", "/api/notifications/read", t=C); assert all(n["read"] for n in c("GET", "/api/notifications", t=C)[1])
assert c("POST", f"/api/orders/{o}/cancel", t=C)[0] == 200
cid = [x for x in c("GET", "/api/admin/customers", t=A)[1] if x["phone"] == "0931111111"][0]["id"]
assert c("PATCH", f"/api/admin/customers/{cid}", {"active": False}, C)[0] == 403 and c("PATCH", f"/api/admin/customers/{cid}", {"active": False}, A)[0] == 200
assert c("GET", "/api/me", t=C)[0] == 401 and c("POST", "/api/login", {"phone": "0931111111", "password": "NewPass1234"})[0] == 401
c("PATCH", f"/api/admin/customers/{cid}", {"active": True}, A); C = L("0931111111", "NewPass1234"); assert C
did = c("POST", "/api/admin/drivers", dict(name="سائق", phone="0921111111", password="DriverPass1", car="a", model="b", year=2020, color="c", plate="1"), A)[1]["id"]
D = L("0921111111", "DriverPass1"); c("PATCH", "/api/me", {"name": "hack"}, D); assert c("GET", "/api/me", t=D)[1]["name"] == "سائق"
assert c("POST", f"/api/admin/drivers/{did}/password", {"password": "NewDriver123"}, D)[0] == 403
assert c("POST", f"/api/admin/drivers/{did}/password", {"password": "short"}, A)[0] == 400
assert c("POST", f"/api/admin/drivers/{did}/password", {"password": "NewDriver123"}, A)[0] == 200
assert c("GET", "/api/me", t=D)[0] == 401 and L("0921111111", "NewDriver123")
acts = [x["action"] for x in c("GET", "/api/admin/audit", t=A)[1]]
assert {"update_profile", "set_customer_active", "reset_driver_password"} <= set(acts) and c("GET", "/api/admin/audit", t=C)[0] == 403
assert "NewDriver123" not in json.dumps(c("GET", "/api/admin/audit", t=A)[1])
c("POST", "/api/register", dict(name="ب", phone="0932222222", password="CustPass123"))
for _ in range(5): assert c("POST", "/api/login", {"phone": "0932222222", "password": "bad"})[0] == 401
assert c("POST", "/api/login", {"phone": "0932222222", "password": "CustPass123"})[0] == 429
print("SECURITY OK")
