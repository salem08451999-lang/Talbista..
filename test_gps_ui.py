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
CH = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
try:
    from playwright.sync_api import sync_playwright
    assert os.path.exists(CH)
except Exception: print("GPS UI OK (browser checks skipped)"); raise SystemExit
A = L("0910000000", "AdminPass123")
c("POST", "/api/admin/drivers", dict(name="سائق", phone="0921111111", password="DriverPass1", car="Kia", model="Rio", year=2020, color="أبيض", plate="P1"), A)
c("POST", "/api/register", dict(name="زبون", phone="0931111111", password="CustPass123"))
GEO = {"latitude": 32.8872, "longitude": 13.1913}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CH, args=["--no-sandbox"]); errs = []
    def page(geo=True):
        ctx = b.new_context(viewport={"width": 390, "height": 844}, locale="ar", is_mobile=True, has_touch=True, device_scale_factor=2, **({"permissions": ["geolocation"], "geolocation": GEO} if geo else {}))
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); return pg
    # driver: GPS position is sent while available
    dp = page(); dp.goto("http://127.0.0.1:8000/driver"); dp.fill("#ph", "0921111111"); dp.fill("#pw", "DriverPass1"); dp.click("#go"); dp.wait_for_selector(".tog"); dp.click(".tog")
    dtok = dp.evaluate("localStorage.getItem('dr')"); until(dp, "document.body.innerText.includes('تم تحديث موقعك')")
    me = c("GET", "/api/me", t=dtok)[1]["driver"]; assert abs(me["lat"] - GEO["latitude"]) < 1e-6 and me["status"] == "AVAILABLE" and me["loc_at"] > 0
    # customer: GPS sets the pickup; the pin can be corrected by tapping the map
    cp = page(); cp.goto("http://127.0.0.1:8000/"); cp.fill("#ph", "0931111111"); cp.fill("#pw", "CustPass123"); cp.click("#go"); cp.wait_for_selector("#new"); cp.click("#new"); cp.wait_for_selector("#ok")
    until(cp, "document.querySelector('[data-s]').textContent.includes('موقعك الحالي')"); cp.screenshot(path="/tmp/cu_map.png", full_page=True)
    box = cp.locator("[data-m]").bounding_box(); cp.mouse.click(box["x"] + box["width"] * .8, box["y"] + box["height"] * .3)
    cp.fill("#dr", "حي الأندلس"); cp.fill("#dt", "طلب"); cp.click("#ok"); cp.wait_for_selector(".tl")
    oid = int(cp.inner_text("main").split("#")[1].split()[0]); full = c("GET", f"/api/orders/{oid}", t=c("POST", "/api/login", {"phone": "0931111111", "password": "CustPass123"})[1]["token"])[1]
    assert full["pickup_lat"] is not None and abs(full["pickup_lat"] - GEO["latitude"]) > 1e-5, "manual correction replaced the GPS point"
    # driver gets the nearest-first offer with distance, accepts, opens the map
    dp.wait_for_selector("[data-a=ac]", timeout=15000); t = dp.inner_text("main"); assert "طلب جديد قريب منك" in t and "يبعد" in t; dp.screenshot(path="/tmp/dr_offer.png", full_page=True)
    dp.click("[data-a=ac]"); dp.wait_for_selector("[data-a=mp]"); dp.click("[data-a=mp]"); dp.wait_for_selector("#mv"); assert dp.locator("#mv div:has-text('📍')").count() >= 1 and dp.locator("#mv div:has-text('🚗')").count() >= 1; dp.screenshot(path="/tmp/dr_map.png")
    # no permission: clear message and manual pin still works
    np_ = page(False); np_.goto("http://127.0.0.1:8000/"); np_.fill("#ph", "0931111111"); np_.fill("#pw", "CustPass123"); np_.click("#go"); np_.wait_for_selector("#new"); np_.click("#new"); np_.wait_for_selector("#ok")
    until(np_, "['لم تسمح','تعذر','انتهت مهلة'].some(x=>document.querySelector('[data-s]').textContent.includes(x))", 30)
    box = np_.locator("[data-m]").bounding_box(); np_.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2); assert "تم تحديد نقطة الاستلام" in np_.inner_text("[data-s]")
    assert errs == [], errs; b.close()
print("GPS UI OK")
