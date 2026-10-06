"""Creates one demo driver and one demo customer through the real API (admin credentials from env)."""
import os, json, secrets, urllib.request as U, urllib.error as X
BASE = os.environ.get("BASE", "http://127.0.0.1:8000")
pw = os.environ.get("DEMO_PASSWORD") or secrets.token_urlsafe(9)


def call(p, b, t=None):
    r = U.Request(BASE + "/api" + p, json.dumps(b).encode(), method="POST", headers={"Authorization": "Bearer " + str(t), "Content-Type": "application/json"})
    try: return json.load(U.urlopen(r))
    except X.HTTPError as e: return {"error": json.load(e).get("error")}


tok = call("/login", {"phone": os.environ.get("ADMIN_PHONE", "0910000000"), "password": os.environ["ADMIN_PASSWORD"]})["token"]
d = call("/admin/drivers", dict(name="سائق تجريبي", phone="0920000001", password=pw, car="Kia", model="Rio", year=2020, color="أبيض", plate="123-456"), tok)
c = call("/register", dict(name="عميل تجريبي", phone="0930000001", password=pw))
print("driver:", "0920000001", "created" if "id" in d else d["error"], "| customer:", "0930000001", "created" if "id" in c else c["error"], "| password:", pw)
