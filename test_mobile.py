import os, json, time, base64, threading, subprocess, tempfile, wave, http.client, urllib.request as U, urllib.error as X
os.environ.update(TALBISTA_DB=":memory:", ADMIN_PASSWORD="AdminPass123", ADMIN_PHONE="0910000000")
import server
from http.server import HTTPServer
calls = []; server.fcm_send = lambda t, m: calls.append((t, m))
server.init(); threading.Thread(target=HTTPServer(("127.0.0.1", 8768), server.H).serve_forever, daemon=True).start()
HERE = os.path.dirname(os.path.abspath(__file__)); M = os.path.join(HERE, "mobile")


def c(m, p, b=None, t=None):
    r = U.Request("http://127.0.0.1:8768" + p, json.dumps(b or {}).encode() if m != "GET" else None, method=m,
                  headers={"Authorization": "Bearer " + str(t), "Content-Type": "application/json"})
    try: x = U.urlopen(r); return x.status, json.loads(x.read())
    except X.HTTPError as e: return e.code, json.loads(e.read())


def wait(pred, s=3):
    for _ in range(int(s * 20)):
        if pred(): return True
        time.sleep(.05)
    return False


L = lambda p, pw: c("POST", "/api/login", {"phone": p, "password": pw})[1].get("token")
A = L("0910000000", "AdminPass123")
c("POST", "/api/admin/drivers", dict(name="سائق", phone="0921111111", password="DriverPass1", car="a", model="b", year=2020, color="c", plate="1"), A)
D = L("0921111111", "DriverPass1"); c("POST", "/api/driver/available", {"available": True}, D)
c("POST", "/api/register", dict(name="عميل", phone="0931111111", password="CustPass123")); C = L("0931111111", "CustPass123")
DT, CT = "d" * 40, "c" * 40
# --- CORS for the app origin ---
k = http.client.HTTPConnection("127.0.0.1", 8768); k.request("OPTIONS", "/api/login", headers={"Origin": "https://localhost"}); r = k.getresponse(); r.read()
assert r.status == 204 and r.getheader("Access-Control-Allow-Origin") == "https://localhost" and "Authorization" in r.getheader("Access-Control-Allow-Headers")
k = http.client.HTTPConnection("127.0.0.1", 8768); k.request("GET", "/healthz", headers={"Origin": "https://evil.example"}); r = k.getresponse(); r.read(); assert r.getheader("Access-Control-Allow-Origin") is None
# --- device tokens ---
assert c("POST", "/api/devices/register", {"token": DT})[0] == 401 and c("POST", "/api/devices/register", {"token": "short"}, D)[0] == 400
assert c("POST", "/api/devices/register", {"token": DT}, D)[0] == 200 and c("POST", "/api/devices/register", {"token": CT}, C)[0] == 200
# --- urgent / normal / status messages ---
mk = lambda u: c("POST", "/api/orders", dict(service_id=1, pickup="أ", dropoff="ب", details="x", urgent=u), C)[1]["id"]
o = mk(True); assert wait(lambda: any(t == DT and m["message"]["data"]["kind"] == "offer" for t, m in calls))
m = [m for t, m in calls if t == DT and m["message"]["data"]["kind"] == "offer"][0]["message"]
assert m["android"]["notification"] == {"channel_id": "talbista_urgent", "sound": "talbista_urgent"} and m["android"]["priority"] == "HIGH"
assert m["data"]["order_id"] == str(o) and m["data"]["urgent"] == "1" and "مستعجل" in m["notification"]["title"]
assert any(t == CT and m_["message"]["android"]["notification"]["channel_id"] == "talbista_default" for t, m_ in calls)
c("POST", f"/api/driver/offers/{o}/accept", {}, D); assert wait(lambda: any(t == CT and m_["message"]["data"].get("kind") == "status" and m_["message"]["data"]["order_id"] == str(o) for t, m_ in calls))
for s in ["DRIVER_ON_THE_WAY", "DRIVER_ARRIVED", "ORDER_PICKED_UP", "ON_THE_WAY_TO_CUSTOMER", "DELIVERED"]: c("POST", f"/api/driver/orders/{o}/status", {"status": s}, D)
n = len(calls); o2 = mk(False); assert wait(lambda: any(t == DT and m_["message"]["android"]["notification"]["channel_id"] == "talbista_offer" for t, m_ in calls[n:]))
# --- same device, other account: token moves ---
assert c("POST", "/api/devices/register", {"token": DT}, C)[0] == 200; n = len(calls); c("POST", f"/api/orders/{o2}/cancel", t=C); o3 = mk(False); time.sleep(.5)
assert not any(t == DT and m_["message"]["data"]["kind"] == "offer" for t, m_ in calls[n:])
c("POST", "/api/devices/unregister", {"token": DT}, C); assert server.q("select 1 from fcm_tokens where token=?", DT) == []
# --- dead token cleanup ---
server.fcm_send = lambda t, m: server.DEAD_TOKENS.append(t); T2 = "x" * 40; c("POST", "/api/devices/register", {"token": T2}, D); mk(False)
assert wait(lambda: T2 in server.DEAD_TOKENS or not server.q("select 1 from fcm_tokens where token=?", T2)); c("GET", "/api/me", t=D); assert server.q("select 1 from fcm_tokens where token=?", T2) == []
# --- FCM OAuth assertion (RS256) ---
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
key = rsa.generate_private_key(65537, 2048); pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
h, p, s = server.fcm_assertion({"client_email": "x@y.iam", "private_key": pem}).split("."); pad = lambda x: x + "=" * (-len(x) % 4)
key.public_key().verify(base64.urlsafe_b64decode(pad(s)), (h + "." + p).encode(), padding.PKCS1v15(), hashes.SHA256())
cl = json.loads(base64.urlsafe_b64decode(pad(p))); assert cl["iss"] == "x@y.iam" and cl["scope"].endswith("firebase.messaging") and cl["aud"] == "https://oauth2.googleapis.com/token"
# --- mobile project checks ---
cfg = json.load(open(M + "/capacitor.config.json")); assert cfg["appId"] == "ly.talbista.app"
assert "@capacitor/push-notifications" in json.load(open(M + "/package.json"))["dependencies"]
for f in os.listdir(M):
    if os.path.isfile(os.path.join(M, f)): assert "watchposition" not in open(os.path.join(M, f), encoding="utf-8").read().lower(), f
env = {**os.environ, "SERVER_URL": "http://insecure.test"}; assert subprocess.run(["python3", "build_www.py"], cwd=M, env=env, capture_output=True).returncode != 0
assert subprocess.run(["python3", "build_www.py"], cwd=M, env={**os.environ, "SERVER_URL": "https://api.example.test"}, capture_output=True).returncode == 0
for f in ("customer.html", "driver.html"):
    t = open(f"{M}/www/{f}", encoding="utf-8").read(); assert 'window.TB_API="https://api.example.test"' in t and 'src="native.js"' in t
assert os.path.exists(M + "/www/app.html") and os.path.exists(M + "/www/native.js")
T = tempfile.mkdtemp(); man = f"{T}/android/app/src/main"; os.makedirs(man); open(f"{T}/gs.json", "w").write("{}")
open(f"{man}/AndroidManifest.xml", "w").write('<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n    <uses-permission android:name="android.permission.INTERNET" />\n    <application android:label="x">\n    </application>\n</manifest>\n')
for _ in range(2): assert subprocess.run(["python3", "apply_android_overlay.py", f"{T}/android"], cwd=M, env={**os.environ, "GOOGLE_SERVICES_JSON_PATH": f"{T}/gs.json", "ALLOW_CLEARTEXT": "1"}, capture_output=True).returncode == 0
mf = open(f"{man}/AndroidManifest.xml", encoding="utf-8").read()
assert all(mf.count(x) == 1 for x in ("POST_NOTIFICATIONS", "android.permission.VIBRATE", "default_notification_channel_id", "usesCleartextTraffic"))
assert os.path.exists(f"{man}/java/ly/talbista/app/MainActivity.java") and os.path.exists(f"{T}/android/app/google-services.json") and os.path.exists(f"{man}/res/raw/talbista_urgent.wav")
assert subprocess.run(["python3", "apply_android_overlay.py", f"{T}/android"], cwd=M, env={k_: v for k_, v in os.environ.items() if k_ != "GOOGLE_SERVICES_JSON_PATH"} | {"GOOGLE_SERVICES_JSON_PATH": "/nonexistent"}, capture_output=True).returncode != 0
w = {n: wave.open(f"{M}/overlay/res/raw/talbista_{n}.wav") for n in ("offer", "urgent")}
assert all(x.getframerate() == 22050 and x.getnchannels() == 1 for x in w.values()) and w["urgent"].getnframes() > w["offer"].getnframes() * .9 and w["urgent"].getnframes() / 22050 > 2
j = open(M + "/overlay/MainActivity.java", encoding="utf-8").read(); assert j.count("{") == j.count("}") and "talbista_urgent" in j and "talbista_offer" in j and "{0, 500, 150" in j
assert subprocess.run(["node", "--check", M + "/native.js"]).returncode == 0
try:
    import yaml; y = yaml.safe_load(open(HERE + "/.github/workflows/android.yml", encoding="utf-8")); assert "build" in y["jobs"]
except ImportError: pass
print("MOBILE OK")
