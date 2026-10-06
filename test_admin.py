import json, urllib.request as U, urllib.error as X


def c(m, p, b=None, t=None):
    r = U.Request("http://127.0.0.1:8000" + p, json.dumps(b or {}).encode() if m != "GET" else None, method=m,
                  headers={"Authorization": "Bearer " + str(t), "Content-Type": "application/json"})
    try:
        x = U.urlopen(r); d = x.read(); return x.status, (d if p == "/admin" else json.loads(d))
    except X.HTTPError as e: return e.code, json.loads(e.read())


s, h = c("GET", "/admin"); assert s == 200 and "لوحة الإدارة".encode() in h
L = lambda p, pw: c("POST", "/api/login", {"phone": p, "password": pw})[1].get("token")
A = L("0910000000", "AdminPass123")
st = c("GET", "/api/admin/stats", t=A)[1]; assert st["drivers"] == 0 and st["customers"] == 0


def drv(ph, pl):
    r = c("POST", "/api/admin/drivers", dict(name="سائق" + pl, phone=ph, password="DriverPass1", car="Kia", model="Rio", year=2020, color="أبيض", plate=pl), A)
    return r[1]["id"], L(ph, "DriverPass1")


d1, D1 = drv("0921111111", "111"); d2, D2 = drv("0922222222", "222")
assert c("POST", "/api/admin/drivers", dict(name="x", phone="0921111111", password="DriverPass1", car="a", model="b", year=1, color="c", plate="d"), A)[0] == 409
for D in (D1, D2): c("POST", "/api/driver/available", {"available": True}, D)
c("POST", "/api/register", dict(name="عميل", phone="0931111111", password="CustPass123")); C = L("0931111111", "CustPass123")
assert len(c("GET", "/api/admin/customers", t=A)[1]) == 1
assert c("PATCH", f"/api/admin/drivers/{d1}", {"car": "Toyota", "plate": "999"}, A)[0] == 200
assert [x for x in c("GET", "/api/admin/drivers", t=A)[1] if x["id"] == d1][0]["car"] == "Toyota"
c("PATCH", f"/api/admin/drivers/{d1}", {"active": False}, A)
assert c("POST", "/api/login", {"phone": "0921111111", "password": "DriverPass1"})[0] == 401
o = c("POST", "/api/orders", dict(service_id=1, pickup="أ", dropoff="ب", details="x"), C)[1]["id"]
assert c("GET", "/api/driver/offers", t=D2)[1][0]["order_id"] == o, "disabled driver skipped"
c("PATCH", f"/api/admin/drivers/{d1}", {"active": True}, A)
assert c("POST", f"/api/admin/orders/{o}/assign", {"driver_id": d1}, A)[0] == 200
g = c("GET", f"/api/orders/{o}", t=C)[1]; assert g["driver"]["plate"] == "999" and g["status"] == "DRIVER_ASSIGNED"
assert c("POST", f"/api/admin/orders/{o}/assign", {"driver_id": d2}, A)[0] == 200 and c("GET", f"/api/orders/{o}", t=C)[1]["driver"]["plate"] == "222"
assert c("POST", f"/api/admin/orders/{o}/cancel", t=A)[0] == 200
assert any(x["id"] == o and x["status"] == "CANCELLED" for x in c("GET", "/api/admin/orders", t=A)[1])
assert c("PUT", "/api/admin/settings", {"auto_dispatch": 0}, A)[0] == 200
o2 = c("POST", "/api/orders", dict(service_id=1, pickup="أ", dropoff="ب", details="x"), C)[1]["id"]
assert c("GET", "/api/driver/offers", t=D1)[1] == [] and c("GET", "/api/driver/offers", t=D2)[1] == [], "dispatch paused"
c("PUT", "/api/admin/settings", {"auto_dispatch": 1, "driver_limit": 5, "normal_base": 20, "commission": 25}, A)
assert c("PUT", "/api/admin/settings", {"commission": -1}, A)[0] == 400 and c("PUT", "/api/admin/settings", {"evil": 1}, A)[0] == 400
sid = c("POST", "/api/admin/services", {"name": "خدمة جديدة"}, A)[1]["id"]; c("PATCH", f"/api/admin/services/{sid}", {"active": False}, A)
assert sid not in [s["id"] for s in c("GET", "/api/services", t=C)[1]] and sid in [s["id"] for s in c("GET", "/api/admin/services", t=A)[1]]
D = [D for D in (D1, D2) if c("GET", "/api/driver/offers", t=D)[1]][0]
c("POST", f"/api/driver/offers/{o2}/accept", {"agreed_price": 30}, D)
for s_ in ["DRIVER_ON_THE_WAY", "DRIVER_ARRIVED", "ORDER_PICKED_UP", "ON_THE_WAY_TO_CUSTOMER", "DELIVERED"]:
    c("POST", f"/api/driver/orders/{o2}/status", {"status": s_}, D)
lg = c("GET", "/api/admin/ledger", t=A)[1]; assert lg[0]["amount"] == 5.0 and lg[0]["pct"] == 25
st = c("GET", "/api/admin/stats", t=A)[1]
assert st["at_limit"] == 1 and st["commissions_total"] == 5 and st["delivered"] == 1 and st["cancelled"] == 1
c("POST", "/api/driver/handover-request", t=D); assert c("GET", "/api/admin/stats", t=A)[1]["handover_requests"] == 1
hid = c("GET", "/api/admin/handovers", t=A)[1][0]["id"]
assert c("POST", f"/api/admin/handovers/{hid}/confirm", t=A)[1]["amount"] == 5
assert c("GET", "/api/admin/stats", t=A)[1]["outstanding_total"] == 0 and c("GET", "/api/admin/ledger", t=A)[1][0]["kind"] == "HANDOVER"
for p in ("/api/admin/customers", "/api/admin/services", "/api/admin/stats", "/api/admin/orders"):
    assert c("GET", p, t=C)[0] == 403 and c("GET", p, t=D)[0] == 403 and c("GET", p)[0] == 401
print("ADMIN OK")
