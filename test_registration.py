import os, json, urllib.request as U, urllib.error as X
HERE = os.path.dirname(os.path.abspath(__file__))


def c(m, p, b=None, t=None):
    r = U.Request("http://127.0.0.1:8000" + p, json.dumps(b or {}).encode() if m != "GET" else None, method=m,
                  headers={"Authorization": "Bearer " + str(t), "Content-Type": "application/json"})
    try: x = U.urlopen(r); return x.status, json.loads(x.read())
    except X.HTTPError as e: return e.code, json.loads(e.read())


L = lambda p, pw: c("POST", "/api/login", {"phone": p, "password": pw})[1]
S = dict(store_name="متجر النور", manager_name="خالد علي", phone="0941111111", address="شارع الجمهورية، طرابلس", activity_type="مطعم", password="StorePass123")
assert c("POST", "/api/register/store", S)[0] == 200
assert c("POST", "/api/register/store", S)[0] == 409
for bad in ({"store_name": ""}, {"password": "short"}, {"phone": "abc"}, {"address": "x"}, {"manager_name": "ع" * 200}, {"activity_type": None}):
    assert c("POST", "/api/register/store", {**S, "phone": "0942222222", **bad})[0] == 400, bad
c("POST", "/api/register", dict(name="زبون", phone="0931111111", password="CustPass123"))
assert c("POST", "/api/register/store", {**S, "phone": "0931111111"})[0] == 409, "one phone = one account across types"
l = L("0941111111", "StorePass123"); assert l["role"] == "STORE" and l["name"] == "متجر النور"; T = l["token"]
m = c("GET", "/api/me", t=T)[1]
assert m["role"] == "STORE" and m["phone"] == "0941111111" and m["store"] == {"store_name": "متجر النور", "manager_name": "خالد علي", "address": "شارع الجمهورية، طرابلس", "activity_type": "مطعم", "lat": None, "lng": None}
assert "store" not in c("GET", "/api/me", t=L("0931111111", "CustPass123")["token"])[1]
# role can never be chosen by the requester
assert c("POST", "/api/register/store", {**S, "phone": "0943333333", "role": "ADMIN"})[0] == 200 and L("0943333333", "StorePass123")["role"] == "STORE"
c("POST", "/api/register", dict(name="x", phone="0944444444", password="CustPass123", role="DRIVER")); assert L("0944444444", "CustPass123")["role"] == "CUSTOMER"
assert c("POST", "/api/register/driver", {**S, "phone": "0945555555"})[0] == 404, "no driver self-registration"
# a store account cannot use customer/driver/admin APIs
for m_, p in (("POST", "/api/orders"), ("GET", "/api/orders"), ("GET", "/api/driver/offers"), ("GET", "/api/admin/stats"), ("POST", "/api/driver/available")): assert c(m_, p, {}, T)[0] == 403, p
assert c("PATCH", "/api/me", {"old_password": "StorePass123", "new_password": "NewStore1234"}, T)[0] == 200 and L("0941111111", "NewStore1234")["role"] == "STORE"
A = L("0910000000", "AdminPass123")["token"]; phones = [x["phone"] for x in c("GET", "/api/admin/customers", t=A)[1]]
assert "0941111111" not in phones and "0931111111" in phones and c("GET", "/api/admin/stats", t=A)[1]["customers"] == 2
print("API OK")
# ---- UI in a phone-size browser ----
CH = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
try:
    from playwright.sync_api import sync_playwright
    assert os.path.exists(CH)
except Exception: print("REGISTRATION OK (browser checks skipped)"); raise SystemExit
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CH, args=["--no-sandbox"]); errs = []
    def page():
        pg = b.new_context(viewport={"width": 390, "height": 844}, locale="ar", is_mobile=True, has_touch=True).new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); pg.goto("http://127.0.0.1:8000/"); return pg
    pg = page(); pg.click("#sw"); assert [pg.inner_text(i).strip() for i in ("#rc", "#rs", "#rd")] == ["زبون", "متجر", "سائق"]
    pg.click("#rd"); assert "تُنشأ من إدارة طلبيستا" in pg.inner_text("main") and pg.locator("input").count() == 0
    pg.click("#bk"); pg.click("#rs"); assert pg.locator("input").count() == 6
    for k, v in (("sn", "متجر الأمل"), ("mn", "سالم"), ("ph", "0946666666"), ("ad", "شارع عمر المختار"), ("at", "صيدلية"), ("pw", "StorePass123")): pg.fill("#" + k, v)
    pg.click("#go"); pg.wait_for_selector("#so"); assert "متجر الأمل" in pg.inner_text("main"); pg.click("#sa"); pg.wait_for_selector("#sl"); t = pg.inner_text("main"); assert "شارع عمر المختار" in t and "صيدلية" in t and "0946666666" in t and "سالم" in t
    pg.reload(); pg.wait_for_selector("#so")  # session + store type survive a reload
    pg.click("#out"); pg.wait_for_selector("#go"); pg.fill("#ph", "0946666666"); pg.fill("#pw", "StorePass123"); pg.click("#go"); pg.wait_for_selector("#so")
    pg2 = page(); pg2.click("#sw"); pg2.click("#rc"); assert pg2.inner_text("h2") == "تسجيل زبون" and pg2.locator("input").count() == 3
    pg2.fill("#n", "زبون جديد"); pg2.fill("#ph", "0947777777"); pg2.fill("#pw", "CustPass123"); pg2.click("#go"); pg2.wait_for_selector("#new")
    assert errs == [], errs; b.close()
print("REGISTRATION OK")
