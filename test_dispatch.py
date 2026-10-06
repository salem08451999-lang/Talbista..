import os, json, time, urllib.request as U, urllib.error as X
os.environ.update(TALBISTA_DB=":memory:", ADMIN_PASSWORD="x")
import server


def c(m, p, b=None, t=None):
    r = U.Request("http://127.0.0.1:8000" + p, json.dumps(b or {}).encode() if m != "GET" else None, method=m,
                  headers={"Authorization": "Bearer " + str(t), "Content-Type": "application/json"})
    try: x = U.urlopen(r); return x.status, json.loads(x.read())
    except X.HTTPError as e: return e.code, json.loads(e.read())


L = lambda p, pw: c("POST", "/api/login", {"phone": p, "password": pw})[1].get("token")
LA, LN = 32.8872, 13.1913; dl = lambda m: m / 111000.0
assert abs(server.hav(LA, LN, LA + dl(400), LN) - 400) < 2 and 111000 < server.hav(0, 0, 0, 1) < 111400   # Haversine
A = L("0910000000", "AdminPass123"); DT = {}; ID = {}
for i in range(1, 7):
    ID[i] = c("POST", "/api/admin/drivers", dict(name=f"سائق{i}", phone=f"092111111{i}", password="DriverPass1", car="Kia", model="Rio", year=2020, color="أبيض", plate=f"P{i}"), A)[1]["id"]; DT[i] = L(f"092111111{i}", "DriverPass1")
c("POST", "/api/register", dict(name="عميل", phone="0931111111", password="CustPass123")); C = L("0931111111", "CustPass123")
offers = lambda i: c("GET", "/api/driver/offers", t=DT[i])[1]; ids = lambda i: sorted(o["order_id"] for o in offers(i))
avail = lambda i, v: c("POST", "/api/driver/available", {"available": v}, DT[i]); loc = lambda i, m: c("POST", "/api/driver/location", {"lat": LA + dl(m), "lng": LN}, DT[i])
mk = lambda urgent=False, pt=True: c("POST", "/api/orders", dict(service_id=1, pickup="أ", dropoff="ب", details="x", urgent=urgent, **({"pickup_lat": LA, "pickup_lng": LN} if pt else {})), C)[1]["id"]
cancel = lambda o: c("POST", f"/api/orders/{o}/cancel", t=C)
setting = lambda **k: c("PUT", "/api/admin/settings", k, A)
# 0) urgent keeps priority; an order with no coordinates still dispatches (fallback)
N = mk(False, pt=False); U_ = mk(True, pt=False); setting(max_active_orders=1); avail(1, True)
assert ids(1) == [U_], "urgent first"
c("POST", f"/api/driver/offers/{U_}/reject", t=DT[1]); assert ids(1) == [N]
c("POST", f"/api/driver/offers/{N}/reject", t=DT[1]); cancel(N); cancel(U_); setting(max_active_orders=2); avail(1, False)
# 1) nearest first, one driver at a time, next nearest on reject / timeout
for i, m in ((1, 400), (2, 800), (3, 1700), (4, 3000)): assert loc(i, m)[0] == 200; avail(i, True)
setting(offer_timeout=2); o = mk()
assert ids(1) == [o] and ids(2) == ids(3) == ids(4) == [], "only the nearest driver gets it"
d = offers(1)[0]["distance_m"]; assert 390 < d < 410 and "pickup_lat" not in offers(1)[0], "approximate distance only, no coordinates before acceptance"
assert "قريب منك" in c("GET", "/api/notifications", t=DT[1])[1][0]["text"] and "يبعد" in c("GET", "/api/notifications", t=DT[1])[1][0]["text"]
c("POST", f"/api/driver/offers/{o}/reject", t=DT[1]); assert ids(2) == [o] and ids(1) == [] and 780 < offers(2)[0]["distance_m"] < 820
c("POST", f"/api/driver/offers/{o}/reject", t=DT[2]); assert ids(3) == [o]
time.sleep(3.3); assert ids(4) == [o] and ids(3) == [], "no answer -> next nearest"
assert c("POST", f"/api/driver/offers/{o}/accept", {}, DT[4])[0] == 200 and ids(1) == ids(2) == ids(3) == []
mine = c("GET", "/api/driver/orders", t=DT[4])[1][0]; assert mine["id"] == o and abs(mine["pickup_lat"] - LA) < 1e-9, "coordinates visible after acceptance"
view = c("GET", f"/api/orders/{o}", t=C)[1]; assert view["driver"]["plate"] == "P4" and "lat" not in view["driver"] and "loc_at" not in view["driver"], "driver position is not exposed to the customer"
setting(offer_timeout=60)
# 2) tie-break: equal distance band -> fresher location wins; distance still beats freshness outside the band
for i in (1, 2, 3, 4): avail(i, False)
avail(5, True); loc(5, 1000); time.sleep(1.2); avail(6, True); loc(6, 1030)
o2 = mk(); assert ids(6) == [o2] and ids(5) == [], "within 100 m band the fresher update wins"
c("POST", f"/api/driver/offers/{o2}/reject", t=DT[6]); assert ids(5) == [o2]; cancel(o2); avail(5, False); avail(6, False)
loc(6, 5000); loc(5, 1000); avail(5, True); avail(6, True); o3 = mk(); assert ids(5) == [o3], "clearly nearer driver wins even if his update is older"; cancel(o3); avail(5, False); avail(6, False)
# 3) at most two active orders (pending offers count), busy driver is skipped
avail(1, True); avail(2, True)
a, b_, c3 = mk(), mk(), mk(); assert ids(1) == sorted([a, b_]) and ids(2) == [c3]
for x in (a, b_): assert c("POST", f"/api/driver/offers/{x}/accept", {}, DT[1])[0] == 200
m = c("GET", "/api/me", t=DT[1])[1]["driver"]; assert m["active_orders"] == 2 and m["status"] == "BUSY"
d4 = mk(); assert d4 in ids(2) and ids(1) == [], "busy driver gets nothing"
for s in ["DRIVER_ON_THE_WAY", "DRIVER_ARRIVED", "ORDER_PICKED_UP", "ON_THE_WAY_TO_CUSTOMER", "DELIVERED"]: assert c("POST", f"/api/driver/orders/{a}/status", {"status": s}, DT[1])[0] == 200
m = c("GET", "/api/me", t=DT[1])[1]["driver"]; assert m["active_orders"] == 1 and m["status"] == "AVAILABLE"
d5 = mk(); assert ids(1) == [d5], "free slot -> nearest driver again"
assert c("GET", "/api/me", t=DT[3])[1]["driver"]["status"] == "UNAVAILABLE"
# 4) validation and ownership of coordinates
for bad in ({"pickup_lat": 91, "pickup_lng": 13}, {"pickup_lat": "abc", "pickup_lng": 13}, {"pickup_lat": 0, "pickup_lng": 0}, {"pickup_lat": 32.8}, {"pickup_lat": 32.8, "pickup_lng": 181}):
    assert c("POST", "/api/orders", dict(service_id=1, pickup="أ", dropoff="ب", details="x", **bad), C)[0] == 400, bad
assert c("POST", "/api/driver/location", {"lat": 95, "lng": 1}, DT[2])[0] == 400 and c("POST", "/api/driver/location", {"lat": LA}, DT[2])[0] == 400
assert c("POST", "/api/driver/location", {"lat": LA, "lng": LN}, C)[0] == 403 and c("POST", "/api/driver/location", {"lat": LA, "lng": LN})[0] == 401
before = {x["id"]: x["lat"] for x in c("GET", "/api/admin/drivers", t=A)[1]}; loc(2, 123)
after = {x["id"]: x["lat"] for x in c("GET", "/api/admin/drivers", t=A)[1]}; assert before[ID[3]] == after[ID[3]] and before[ID[2]] != after[ID[2]], "a driver can only move himself"
print("DISPATCH OK")
