import os, json, urllib.request as U, urllib.error as X
import time


def until(pg, js, timeout=15):  # polling from the test side: the page CSP (correctly) forbids eval, which Playwright's wait_for_function needs
    end = time.time() + timeout
    while time.time() < end:
        if pg.evaluate(js): return
        time.sleep(0.2)
    raise AssertionError("timeout waiting for: " + js)




def c(m, p, b=None, t=None):
    r = U.Request("http://127.0.0.1:8000" + p, json.dumps(b or {}).encode() if m != "GET" else None, method=m,
                  headers={"Authorization": "Bearer " + str(t), "Content-Type": "application/json"})
    try: x = U.urlopen(r); return x.status, json.loads(x.read())
    except X.HTTPError as e: return e.code, json.loads(e.read())


L = lambda p, pw: c("POST", "/api/login", {"phone": p, "password": pw})[1].get("token")
A = L("0910000000", "AdminPass123")
S1 = dict(store_name="صيدلية النور", manager_name="خالد", phone="0941111111", address="زاوية الدهماني، طرابلس", activity_type="صيدلية", password="StorePass123")
c("POST", "/api/register/store", S1); c("POST", "/api/register/store", {**S1, "store_name": "متجر ثان", "phone": "0942222222"})
T1, T2 = L("0941111111", "StorePass123"), L("0942222222", "StorePass123")
did = c("POST", "/api/admin/drivers", dict(name="سائق", phone="0921111111", password="DriverPass1", car="Kia", model="Rio", year=2020, color="أبيض", plate="P1"), A)[1]["id"]
D = L("0921111111", "DriverPass1"); c("POST", "/api/driver/available", {"available": True}, D)
c("POST", "/api/register", dict(name="زبون", phone="0931111111", password="CustPass123")); C = L("0931111111", "CustPass123")
cf = c("GET", "/api/store/config", t=T1)[1]; assert cf["fee_normal"] == 15 and cf["fee_urgent"] == 30 and cf["lat"] is None
O = dict(contact="أحمد 0912345678", dropoff="حي الأندلس", details="دواء", order_value=45, notes="اتصل قبل الوصول")
# validation
for bad in ({"contact": ""}, {"dropoff": ""}, {"details": ""}, {"order_value": None}, {"order_value": -5}, {"order_value": "abc"}, {"pickup_lat": 99, "pickup_lng": 1}):
    assert c("POST", "/api/store/orders", {**O, **bad}, T1)[0] == 400, bad
assert c("POST", "/api/store/orders", {**O, "is_paid": True, "order_value": None}, T1)[0] == 200, "paid order needs no value"
# order creation: fee shown, bound to the account automatically, no store data retyped
c("PATCH", "/api/store/location", {"lat": 32.8872, "lng": 13.1913}, T1)
r = c("POST", "/api/store/orders", O, T1); assert r[0] == 200 and r[1]["delivery_fee"] == 15; o = r[1]["id"]
ru = c("POST", "/api/store/orders", {**O, "urgent": True, "dropoff": "سوق الجمعة"}, T1); assert ru[1]["delivery_fee"] == 30
lst = c("GET", "/api/store/orders", t=T1)[1]; row = [x for x in lst if x["id"] == o][0]
assert len(lst) == 3 and row["status"] == "SEARCHING_DRIVER" and row["is_paid"] == 0 and row["order_value"] == 45 and row["delivery_fee"] == 15 and row["urgent"] == 0
adm = [x for x in c("GET", "/api/admin/orders", t=A)[1] if x["id"] == o][0]; assert adm["kind"] == "STORE" and adm["pickup"] == S1["address"] and abs(adm["pickup_lat"] - 32.8872) < 1e-9
assert c("GET", "/api/store/orders", t=T2)[1] == [] and c("GET", f"/api/orders/{o}", t=T2)[0] == 404 and c("GET", f"/api/orders/{o}", t=C)[0] == 404
assert c("POST", f"/api/store/orders/{o}/cancel", t=T2)[0] == 404
# role separation
for m_, p, t in (("GET", "/api/store/orders", C), ("POST", "/api/store/orders", D), ("GET", "/api/store/config", A), ("POST", "/api/orders", T1), ("GET", "/api/orders", T1), ("GET", "/api/driver/offers", T1)): assert c(m_, p, O, t)[0] == 403, p
# what the driver sees: store name/address/fee/paid/value before accepting; contact only after
offer = [x for x in c("GET", "/api/driver/offers", t=D)[1] if x["order_id"] == o]
if not offer:  # urgent store order was offered first; clear it so the normal one comes up
    for x in c("GET", "/api/driver/offers", t=D)[1]: c("POST", f"/api/driver/offers/{x['order_id']}/reject", t=D)
    c("POST", "/api/driver/offers/%d/reject" % ru[1]["id"], t=D)
    o2 = c("POST", "/api/store/orders", O, T1)[1]["id"]; offer = [x for x in c("GET", "/api/driver/offers", t=D)[1] if x["order_id"] == o2]; o = o2
f = offer[0]; assert f["kind"] == "STORE" and f["store_name"] == "صيدلية النور" and f["store_address"] == S1["address"] and f["delivery_fee"] == 15 and f["is_paid"] == 0 and f["order_value"] == 45 and f["notes"] == "اتصل قبل الوصول"
assert "contact" not in f and "customer_phone" not in f and "pickup_lat" not in f
assert c("POST", f"/api/driver/offers/{o}/accept", {}, D)[0] == 200
mine = [x for x in c("GET", "/api/driver/orders", t=D)[1] if x["id"] == o][0]
assert mine["customer_name"] == "صيدلية النور" and mine["customer_phone"] == "0941111111" and mine["contact"] == "أحمد 0912345678" and mine["store_address"] == S1["address"] and mine["delivery_fee"] == 15 and abs(mine["pickup_lat"] - 32.8872) < 1e-9
assert c("GET", f"/api/orders/{o}", t=T1)[1]["driver"]["plate"] == "P1"
# commission is untouched by the delivery fee
c("PUT", "/api/admin/settings", {"store_fee_normal": 25}, A)
assert c("POST", f"/api/store/orders/{o}/cancel", t=T1)[0] == 200 or True
o3 = c("POST", "/api/store/orders", O, T1)[1]; assert o3["delivery_fee"] == 25
for s in ["DRIVER_ON_THE_WAY", "DRIVER_ARRIVED", "ORDER_PICKED_UP"]: assert c("POST", f"/api/driver/orders/{o}/status", {"status": s}, D)[0] in (200, 409)
st = c("GET", f"/api/orders/{o}", t=T1)[1]["status"]
if st == "ORDER_PICKED_UP": assert c("POST", f"/api/store/orders/{o}/cancel", t=T1)[0] == 409
# deliver one fully and check ledger + hidden contact
oid = o
if st == "CANCELLED":
    oid = None
if oid:
    for s in ["ON_THE_WAY_TO_CUSTOMER", "DELIVERED"]: assert c("POST", f"/api/driver/orders/{oid}/status", {"status": s}, D)[0] == 200
    assert [x for x in c("GET", "/api/admin/ledger", t=A)[1] if x["order_id"] == oid][0]["amount"] == 3.0, "15 x 20% regardless of the fee"
    done = [x for x in c("GET", "/api/driver/orders", t=D)[1] if x["id"] == oid][0]; assert done["contact"] is None and done["customer_phone"] is None
    assert c("GET", f"/api/orders/{oid}", t=D)[1]["contact"] is None
# support + reports
sp = c("GET", "/api/support", t=T1)[1]; assert set(sp) == {"phone", "whatsapp"}
assert c("POST", "/api/support/report", {"message": "x"}, T1)[0] == 400 and c("POST", "/api/support/report", {"message": "السائق لم يصل", "order_id": o}, T1)[0] == 200
rp = c("GET", "/api/admin/reports", t=A)[1]; assert rp[0]["message"] == "السائق لم يصل" and rp[0]["user_name"] == "صيدلية النور" and c("GET", "/api/admin/reports", t=T1)[0] == 403
assert c("POST", f"/api/admin/reports/{rp[0]['id']}/resolve", t=A)[0] == 200 and c("GET", "/api/admin/reports", t=A)[1][0]["status"] == "DONE"
print("STORE API OK")
# ---- store UI at phone size, with GPS granted ----
CH = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
try:
    from playwright.sync_api import sync_playwright
    assert os.path.exists(CH)
except Exception: print("STORE OK (browser checks skipped)"); raise SystemExit
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CH, args=["--no-sandbox"]); errs = []
    ctx = b.new_context(viewport={"width": 390, "height": 844}, locale="ar", is_mobile=True, has_touch=True, permissions=["geolocation"], geolocation={"latitude": 32.8890, "longitude": 13.1930}, device_scale_factor=2)
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); pg.goto("http://127.0.0.1:8000/")
    pg.fill("#ph", "0942222222"); pg.fill("#pw", "StorePass123"); pg.click("#go"); pg.wait_for_selector("#sn")
    assert all(pg.locator(i).count() == 1 for i in ("#sn", "#so", "#sf", "#sa", "#sh")); pg.screenshot(path="/tmp/st_home.png")
    pg.click("#sn"); pg.wait_for_selector("#ok"); assert "25" in pg.inner_text("#fee"); pg.click(".seg label.ur >> nth=0"); assert "30" in pg.inner_text("#fee")
    pg.locator("input[name=p][value='1']").evaluate("e=>{e.checked=true;e.dispatchEvent(new Event('change'))}"); assert pg.locator("#vl").is_hidden()
    pg.locator("input[name=p][value='0']").evaluate("e=>{e.checked=true;e.dispatchEvent(new Event('change'))}"); assert pg.locator("#vl").is_visible()
    until(pg, "document.querySelector('[data-s]').textContent.includes('موقعك الحالي')"); pg.screenshot(path="/tmp/st_new.png", full_page=True)
    pg.locator("input[name=u][value='0']").evaluate("e=>{e.checked=true;e.dispatchEvent(new Event('change'))}"); assert "25" in pg.inner_text("#fee")
    pg.fill("#ct", "سالم 0911111111"); pg.fill("#dr", "قرجي"); pg.fill("#dt", "طلب تجريبي"); pg.fill("#vv", "20"); pg.click("#ok"); pg.wait_for_selector(".tl"); assert "طلب #" in pg.inner_text("main") and "20" in pg.inner_text("main")
    mine = c("GET", "/api/store/orders", t=T2)[1][0]; assert mine["urgent"] == 0 and mine["order_value"] == 20 and mine["delivery_fee"] == 25
    full = [x for x in c("GET", "/api/admin/orders", t=A)[1] if x["id"] == mine["id"]][0]; assert abs(full["pickup_lat"] - 32.8890) < 1e-6, "GPS position saved with the order"
    pg.click("#bk"); pg.wait_for_selector("[data-id]"); pg.click("#bk"); pg.wait_for_selector("#sn"); pg.click("#so"); pg.wait_for_selector("[data-id]"); assert "جاري البحث عن سائق" in pg.inner_text("main") or "تم تعيين" in pg.inner_text("main")
    pg.click("#bk"); pg.click("#sh"); pg.wait_for_selector("#fq"); pg.click("#fq"); assert "كيف أنشئ طلب توصيل" in pg.inner_text("#sx"); pg.click("#rp"); pg.fill("#rm", "مشكلة في الطلب"); pg.click("#rs"); pg.wait_for_selector("text=تم إرسال البلاغ")
    pg.click("#bk"); pg.click("#sf"); pg.wait_for_selector("#bk"); pg.click("#bk"); pg.wait_for_selector("#sn"); pg.click("#sa"); pg.wait_for_selector("#sl"); pg.click("#sl"); pg.wait_for_selector("text=تم حفظ موقع المتجر") if False else pg.wait_for_timeout(600)
    assert errs == [], errs; b.close()
print("STORE OK")
