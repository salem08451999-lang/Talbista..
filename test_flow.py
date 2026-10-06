import os, json, threading, urllib.request, urllib.error
os.environ.update(TALBISTA_DB=":memory:", ADMIN_PASSWORD="AdminPass123", ADMIN_PHONE="0910000000")
import server
from http.server import HTTPServer
server.init()
threading.Thread(target=HTTPServer(("127.0.0.1", 8765), server.H).serve_forever, daemon=True).start()


def call(m, p, b=None, t=None):
    r = urllib.request.Request("http://127.0.0.1:8765" + p, json.dumps(b or {}).encode(), method=m,
                               headers={"Authorization": "Bearer " + t} if t else {})
    try:
        with urllib.request.urlopen(r) as x: return x.status, json.load(x)
    except urllib.error.HTTPError as e: return e.code, json.load(e)


def login(ph, pw): return call("POST", "/api/login", {"phone": ph, "password": pw})[1]["token"]


A = login("0910000000", "AdminPass123")
_, d = call("POST", "/api/admin/drivers", dict(name="سائق", phone="0921111111", password="DriverPass1", car="Kia", model="Rio", year=2020, color="أبيض", plate="123-456"), A)
D = login("0921111111", "DriverPass1"); call("POST", "/api/driver/available", {"available": True}, D)
call("POST", "/api/register", dict(name="عميل", phone="0931111111", password="CustPass123")); C = login("0931111111", "CustPass123")
call("PUT", "/api/admin/settings", {"driver_limit": 8}, A)


def run(urgent):
    _, o = call("POST", "/api/orders", dict(service_id=1, pickup="أ", dropoff="ب", details="x", urgent=urgent, commission=0, driver_id=999), C)
    offers = call("GET", "/api/driver/offers", t=D)[1]; assert offers and offers[0]["order_id"] == o["id"], "auto dispatch"
    assert call("POST", f"/api/driver/offers/{o['id']}/accept", {"agreed_price": 20}, D)[0] == 200
    assert call("GET", f"/api/orders/{o['id']}", t=C)[1]["driver"]["plate"] == "123-456"
    for st in server.FLOW[1:]: assert call("POST", f"/api/driver/orders/{o['id']}/status", {"status": st}, D)[0] == 200
    assert call("POST", f"/api/orders/{o['id']}/confirm", t=C)[0] == 200
    assert call("POST", f"/api/orders/{o['id']}/rate", {"stars": 5}, C)[0] == 200
    return o["id"]


run(0); assert call("GET", "/api/me", t=D)[1]["driver"]["outstanding"] == 3
run(1); assert call("GET", "/api/me", t=D)[1]["driver"]["outstanding"] == 9
_, o3 = call("POST", "/api/orders", dict(service_id=1, pickup="أ", dropoff="ب", details="x"), C)
assert call("GET", "/api/driver/offers", t=D)[1] == [], "blocked at limit"
assert call("GET", "/api/admin/stats", t=C)[0] == 403 and call("PUT", "/api/admin/settings", {"commission": 0}, D)[0] == 403
assert call("POST", "/api/admin/drivers", {}, D)[0] == 403
call("POST", "/api/driver/handover-request", t=D)
assert call("POST", "/api/admin/handovers/1/confirm", t=D)[0] == 403
assert call("POST", "/api/admin/handovers/1/confirm", t=A)[1]["amount"] == 9
assert call("GET", "/api/me", t=D)[1]["driver"]["outstanding"] == 0
assert len(call("GET", "/api/driver/offers", t=D)[1]) == 1, "eligible again"
try: server.ex("delete from ledger"); assert 0
except Exception as e: assert "immutable" in str(e)
print("ALL TESTS PASSED")
