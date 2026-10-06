import sys, json, urllib.request as U, urllib.error as X
def c(m, p, b=None, t=None):
    r = U.Request("http://127.0.0.1:8000" + p, json.dumps(b or {}).encode() if m != "GET" else None, method=m, headers={"Authorization": "Bearer " + str(t), "Content-Type": "application/json"})
    try: x = U.urlopen(r); return x.status, json.loads(x.read())
    except X.HTTPError as e: return e.code, json.loads(e.read())
L = lambda p, pw: c("POST", "/api/login", {"phone": p, "password": pw})[1]["token"]
if sys.argv[1] == "1":  # before the "app/server restart"
    A = L("0910000000", "AdminPass123"); c("POST", "/api/admin/drivers", dict(name="س", phone="0921111111", password="DriverPass1", car="a", model="b", year=1, color="c", plate="1"), A)
    D = L("0921111111", "DriverPass1"); c("POST", "/api/driver/available", {"available": True}, D)
    c("POST", "/api/register", dict(name="ع", phone="0931111111", password="CustPass123")); C = L("0931111111", "CustPass123")
    o = c("POST", "/api/orders", dict(service_id=1, pickup="أ", dropoff="ب", details="x"), C)[1]["id"]
    c("POST", f"/api/driver/offers/{o}/accept", {"agreed_price": 20}, D); c("POST", f"/api/driver/orders/{o}/status", {"status": "DRIVER_ON_THE_WAY"}, D)
    json.dump({"o": o, "C": C, "D": D}, open("/tmp/restart.json", "w"))
else:  # after restart: same tokens, state intact, flow continues
    S = json.load(open("/tmp/restart.json")); v = c("GET", f"/api/orders/{S['o']}", t=S["C"])
    assert v[0] == 200 and v[1]["status"] == "DRIVER_ON_THE_WAY" and len(v[1]["history"]) == 4 and v[1]["driver"]["plate"] == "1"
    assert c("GET", "/api/me", t=S["D"])[1]["driver"]["available"] == 1
    for s in ["DRIVER_ARRIVED", "ORDER_PICKED_UP", "ON_THE_WAY_TO_CUSTOMER", "DELIVERED"]: assert c("POST", f"/api/driver/orders/{S['o']}/status", {"status": s}, S["D"])[0] == 200
    assert c("GET", "/api/me", t=S["D"])[1]["driver"]["outstanding"] == 3
    print("RESTART OK")
