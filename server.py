import os, json, re, sqlite3, hashlib, secrets, time, math
from http.server import BaseHTTPRequestHandler, HTTPServer

db = sqlite3.connect(os.environ.get("TALBISTA_DB", "talbista.db"), check_same_thread=False)
db.row_factory = sqlite3.Row
SCHEMA = """
create table if not exists users(id integer primary key,role text,name text,phone text unique,pw text,active int default 1,photo text);
create table if not exists drivers(user_id integer primary key,car text,model text,year int,color text,plate text,docs text,available int default 0,outstanding real default 0,last_offer int default 0,rating_sum int default 0,rating_n int default 0);
create table if not exists sessions(token text primary key,user_id int,exp int);
create table if not exists services(id integer primary key,name text,active int default 1);
create table if not exists orders(id integer primary key,customer_id int,service_id int,pickup text,dropoff text,details text,urgent int,status text,driver_id int,agreed_price real,created int,confirmed int default 0);
create table if not exists order_status_history(id integer primary key,order_id int,status text,actor int,at int);
create table if not exists offers(id integer primary key,order_id int,driver_id int,status text,expires int);
create table if not exists ratings(order_id int primary key,driver_id int,customer_id int,stars int,comment text);
create table if not exists notifications(id integer primary key,user_id int,text text,at int,read int default 0);
create table if not exists ledger(id integer primary key,at int,driver_id int,order_id int,kind text,urgent int,base real,pct real,amount real,balance_after real,admin_id int,note text);
create table if not exists cash_handovers(id integer primary key,driver_id int,status text,requested int,amount real,confirmed_at int,admin_id int);
create table if not exists audit_logs(id integer primary key,at int,actor int,action text,detail text);
create table if not exists settings(k text primary key,v real);
create table if not exists kv(k text primary key,v text);
create table if not exists stores(user_id integer primary key,store_name text,manager_name text,address text,activity_type text);
create table if not exists reports(id integer primary key,user_id int,order_id int,message text,created int,status text);
create table if not exists fcm_tokens(token text primary key,user_id int,created int);
create table if not exists push_subs(endpoint text primary key,user_id int,created int);
create table if not exists violations(id integer primary key,driver_id int,order_id int,reason text,fine real,created int,blocked_until int,status text,admin_id int,cancelled_by int,cancelled_at int,cancel_note text);
create trigger if not exists l_nu before update on ledger begin select raise(abort,'ledger immutable'); end;
create trigger if not exists l_nd before delete on ledger begin select raise(abort,'ledger immutable'); end;
"""
DEFAULTS = {"commission": 20, "normal_base": 15, "urgent_base": 30, "driver_limit": 100,
            "offer_timeout": 60, "auto_dispatch": 1, "violation_fine": 10, "violation_block_hours": 24,
            "max_active_orders": 2, "location_max_age": 600, "store_fee_normal": 15, "store_fee_urgent": 30}
FLOW = ["DRIVER_ASSIGNED", "DRIVER_ON_THE_WAY", "DRIVER_ARRIVED", "ORDER_PICKED_UP", "ON_THE_WAY_TO_CUSTOMER", "DELIVERED"]
OPEN = "('DELIVERED','CANCELLED')"
FAILS = {}
DEAD_TOKENS = []
ALLOWED_ORIGINS = set(os.environ.get("CORS_ORIGINS", "https://localhost,capacitor://localhost,http://localhost").split(","))
SEC = [("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY"), ("Referrer-Policy", "no-referrer"), ("Cache-Control", "no-store"),
       ("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data: https:; frame-ancestors 'none'")]


class Err(Exception):
    def __init__(s, code, msg): s.code, s.msg = code, msg


def q(sql, *a): return [dict(r) for r in db.execute(sql, a).fetchall()]
def one(sql, *a):
    r = q(sql, *a); return r[0] if r else None
def ex(sql, *a): return db.execute(sql, a)
def now(): return int(time.time())
def S(k): return one("select v from settings where k=?", k)["v"]


def hpw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200000).hex()


def chk(pw, stored):
    return secrets.compare_digest(hpw(pw, stored.split("$")[0]), stored)


def notify(uid, text, order_id=None, urgent=0, kind="info"):
    ex("insert into notifications(user_id,text,at) values(?,?,?)", uid, text, now()); fcm_push(uid, text, order_id, urgent, kind)
def audit(actor, action, detail=""): ex("insert into audit_logs(at,actor,action,detail) values(?,?,?,?)", now(), actor, action, json.dumps(detail, ensure_ascii=False))
def hist(oid, st, actor): ex("insert into order_status_history(order_id,status,actor,at) values(?,?,?,?)", oid, st, actor, now())
def need(b, *keys):
    for k in keys:
        if b.get(k) in (None, ""): raise Err(400, f"missing {k}")


import base64, threading, urllib.request, urllib.parse, urllib.error
_P = 0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff
_N = 0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551
_A = _P - 3
_G = (0x6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296, 0x4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5)
PUSH_HOSTS = ("googleapis.com", "push.services.mozilla.com", "push.apple.com", "notify.windows.com")
VAPID_D = VAPID_PUB = None


def b64(x): return base64.urlsafe_b64encode(x).rstrip(b"=").decode()


def _add(p, q_):
    if p is None: return q_
    if q_ is None: return p
    if p[0] == q_[0] and (p[1] + q_[1]) % _P == 0: return None
    l = (3 * p[0] * p[0] + _A) * pow(2 * p[1], -1, _P) % _P if p == q_ else (q_[1] - p[1]) * pow(q_[0] - p[0], -1, _P) % _P
    x = (l * l - p[0] - q_[0]) % _P
    return (x, (l * (p[0] - x) - p[1]) % _P)


def _mul(k, p):
    r = None
    while k:
        if k & 1: r = _add(r, p)
        p = _add(p, p); k >>= 1
    return r


def init_vapid():
    global VAPID_D, VAPID_PUB
    if not one("select v from kv where k='vapid'"): ex("insert into kv values('vapid',?)", hex(secrets.randbelow(_N - 1) + 1))
    VAPID_D = int(one("select v from kv where k='vapid'")["v"], 16); x, y = _mul(VAPID_D, _G)
    VAPID_PUB = b64(b"\x04" + x.to_bytes(32, "big") + y.to_bytes(32, "big"))


def es256(msg):
    h = int.from_bytes(hashlib.sha256(msg).digest(), "big")
    while True:
        k = secrets.randbelow(_N - 1) + 1; r = _mul(k, _G)[0] % _N
        s_ = pow(k, -1, _N) * (h + r * VAPID_D) % _N
        if r and s_: return r.to_bytes(32, "big") + s_.to_bytes(32, "big")


def vapid_header(endpoint):
    u = urllib.parse.urlparse(endpoint)
    hd = b64(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())
    cl = b64(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": now() + 43200, "sub": os.environ.get("VAPID_SUB", "mailto:admin@talbista.example")}).encode())
    return f"vapid t={hd}.{cl}.{b64(es256((hd + '.' + cl).encode()))}, k={VAPID_PUB}"


def push_send(endpoint, auth):
    try:
        urllib.request.urlopen(urllib.request.Request(endpoint, data=b"", method="POST", headers={"Authorization": auth, "TTL": "60", "Urgency": "high"}), timeout=5).read()
    except Exception: pass


def push(uid):
    for r in q("select endpoint from push_subs where user_id=?", uid):
        threading.Thread(target=lambda e=r["endpoint"]: push_send(e, vapid_header(e)), daemon=True).start()


FCM_SA = None
_FCM_TOK = [None, 0]


def fcm_load():
    global FCM_SA
    raw = os.environ.get("FCM_SERVICE_ACCOUNT_JSON", "").strip()
    if raw: FCM_SA = json.loads(raw) if raw.startswith("{") else json.load(open(raw))


def fcm_assertion(sa):  # OAuth2 service-account JWT (RS256); needs the `cryptography` package
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    iat = now(); hd = b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    cl = b64(json.dumps({"iss": sa["client_email"], "scope": "https://www.googleapis.com/auth/firebase.messaging",
                         "aud": "https://oauth2.googleapis.com/token", "iat": iat, "exp": iat + 3600}).encode())
    key = serialization.load_pem_private_key(sa["private_key"].encode(), None)
    return f"{hd}.{cl}." + b64(key.sign((hd + "." + cl).encode(), padding.PKCS1v15(), hashes.SHA256()))


def fcm_access():
    if _FCM_TOK[0] and _FCM_TOK[1] > now() + 60: return _FCM_TOK[0]
    body = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": fcm_assertion(FCM_SA)}).encode()
    r = json.load(urllib.request.urlopen(urllib.request.Request(FCM_SA.get("token_uri", "https://oauth2.googleapis.com/token"), body, method="POST"), timeout=10))
    _FCM_TOK[:] = [r["access_token"], now() + int(r.get("expires_in", 3600))]; return _FCM_TOK[0]


def fcm_message(token, title, body, data, channel, offer):
    n = {"channel_id": channel}
    if offer: n["sound"] = channel  # raw resource name (pre-Android 8); Android 8+ uses the channel's sound/vibration
    return {"message": {"token": token, "notification": {"title": title, "body": body}, "data": {k: str(v) for k, v in data.items()},
                        "android": {"priority": "HIGH", "ttl": "60s" if offer else "3600s", "notification": n}}}


def fcm_send(token, msg):
    if not FCM_SA: return
    try:
        urllib.request.urlopen(urllib.request.Request(f"https://fcm.googleapis.com/v1/projects/{FCM_SA['project_id']}/messages:send", json.dumps(msg).encode(), method="POST",
                               headers={"Authorization": "Bearer " + fcm_access(), "Content-Type": "application/json"}), timeout=10).read()
    except urllib.error.HTTPError as e:
        if e.code == 404 or b"UNREGISTERED" in e.read(): DEAD_TOKENS.append(token)
    except Exception: pass


def fcm_push(uid, text, order_id, urgent, kind):
    offer = kind == "offer"; ch = ("talbista_urgent" if urgent else "talbista_offer") if offer else "talbista_default"
    title = ("⚡ طلب مستعجل قريب منك" if urgent else "🚚 طلب جديد قريب منك") if offer else "طلبيستا"
    data = {"kind": kind, "urgent": 1 if urgent else 0}
    if order_id: data["order_id"] = order_id
    for r in q("select token from fcm_tokens where user_id=?", uid):
        threading.Thread(target=fcm_send, args=(r["token"], fcm_message(r["token"], title, text, data, ch, offer)), daemon=True).start()


def init():
    db.executescript(SCHEMA); db.execute("pragma journal_mode=wal"); db.execute("delete from sessions where exp<?", (now(),))
    try: db.execute("alter table drivers add column blocked_until int default 0")
    except sqlite3.OperationalError: pass
    for t_, c_ in (("orders", "kind text default 'CUSTOMER'"), ("orders", "contact text"), ("orders", "order_value real"), ("orders", "is_paid int default 0"), ("orders", "delivery_fee real"),
                   ("orders", "notes text"), ("orders", "pickup_lat real"), ("orders", "pickup_lng real"), ("orders", "dropoff_lat real"), ("orders", "dropoff_lng real"),
                   ("drivers", "lat real"), ("drivers", "lng real"), ("drivers", "loc_at int default 0"), ("stores", "lat real"), ("stores", "lng real"), ("offers", "distance_m real")):
        try: db.execute(f"alter table {t_} add column {c_}")
        except sqlite3.OperationalError: pass
    db.execute("create index if not exists drv_geo on drivers(available,lat,lng)")
    init_vapid(); fcm_load()
    for k, v in DEFAULTS.items(): ex("insert or ignore into settings values(?,?)", k, v)
    if not q("select 1 from services"):
        for n in ["شراء من مطعم", "شراء من محل", "استلام أمانة/طرد", "توصيل مستندات", "مشوار خاص", "مهمة أخرى"]:
            ex("insert into services(name) values(?)", n)
    if not q("select 1 from users where role='ADMIN'"):
        pw = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(10)
        ph = os.environ.get("ADMIN_PHONE", "0910000000")
        ex("insert into users(role,name,phone,pw) values('ADMIN','Admin',?,?)", ph, hpw(pw))
        if not os.environ.get("ADMIN_PASSWORD"): print("ADMIN", ph, pw)
    db.commit()


def coord(b, ka, kb):
    la, ln = b.get(ka), b.get(kb)
    if la is None and ln is None: return None, None
    try: la, ln = float(la), float(ln)
    except (TypeError, ValueError): raise Err(400, "bad coordinates")
    if not (-90 <= la <= 90 and -180 <= ln <= 180) or (la == 0 and ln == 0): raise Err(400, "bad coordinates")
    return la, ln


def hav(la1, ln1, la2, ln2):  # great-circle distance in metres (Haversine)
    p = math.pi / 180; x = math.sin((la2 - la1) * p / 2) ** 2 + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((ln2 - ln1) * p / 2) ** 2
    return 12742000 * math.asin(math.sqrt(x))


def fmt_dist(m): return f"{m / 1000:.1f} كم" if m >= 1000 else f"{int(round(m, -1))} متر"


RADII = (5, 15, 50, 500)  # km: bounding boxes widen only when nobody is found (indexed lookups, no full scan first)
TIE_M = 100               # distances within the same 100 m band count as "about equal" -> fresher location wins
ELIG = """u.active=1 and d.available=1 and d.outstanding<? and d.blocked_until<=?
    and (select count(*) from orders x where x.driver_id=u.id and x.status not in ('DELIVERED','CANCELLED'))
      + (select count(*) from offers p where p.driver_id=u.id and p.status='PENDING') < ?
    and not exists(select 1 from offers f where f.driver_id=u.id and f.order_id=?)"""


def pick_driver(o, t):
    """Nearest eligible driver with a fresh location; drivers without one are the fallback (never random among located ones)."""
    base = (S("driver_limit"), t, S("max_active_orders"), o["id"]); la, ln = o["pickup_lat"], o["pickup_lng"]
    if la is not None and ln is not None:
        fresh = t - int(S("location_max_age"))
        for km in RADII:
            dl = km / 111.0; dg = km / (111.0 * max(math.cos(math.radians(la)), 0.05))
            rows = q("select u.id,d.lat,d.lng,d.loc_at from users u join drivers d on d.user_id=u.id where " + ELIG + " and d.loc_at>=? and d.lat between ? and ? and d.lng between ? and ?",
                     *base, fresh, la - dl, la + dl, ln - dg, ln + dg)
            rows = [dict(r, dist=hav(la, ln, r["lat"], r["lng"])) for r in rows]; rows = [r for r in rows if r["dist"] <= km * 1000]
            if rows:
                rows.sort(key=lambda r: (int(r["dist"] // TIE_M), -r["loc_at"], r["dist"], r["id"]))
                return rows[0]["id"], rows[0]["dist"]
    r = one("select u.id from users u join drivers d on d.user_id=u.id where " + ELIG + " order by d.last_offer limit 1", *base)
    return (r["id"], None) if r else (None, None)


def dispatch():
    """Sequential nearest-first dispatch: one pending offer per order; reject/timeout moves to the next nearest driver."""
    while DEAD_TOKENS: ex("delete from fcm_tokens where token=?", DEAD_TOKENS.pop())
    if S("auto_dispatch") == 0: return
    t = now(); ex("update offers set status='EXPIRED' where status='PENDING' and expires<?", t)
    for o in q("select * from orders where status='SEARCHING_DRIVER' order by urgent desc,id"):
        if one("select 1 from offers where order_id=? and status='PENDING'", o["id"]): continue
        d, dist = pick_driver(o, t)
        if d is None: continue
        ex("insert into offers(order_id,driver_id,status,expires,distance_m) values(?,?,'PENDING',?,?)", o["id"], d, t + int(S("offer_timeout")), dist)
        ex("update drivers set last_offer=? where user_id=?", t, d)
        notify(d, ("⚡ طلب مستعجل قريب منك" if o["urgent"] else "🚚 طلب جديد قريب منك") + f" #{o['id']}" + (f" - يبعد {fmt_dist(dist)}" if dist is not None else ""),
               order_id=o["id"], urgent=o["urgent"], kind="offer"); push(d)


def set_status(o, st, actor):
    ex("update orders set status=? where id=?", st, o["id"]); hist(o["id"], st, actor)
    if st == "DELIVERED" and o["driver_id"]:
        base = S("urgent_base") if o["urgent"] else S("normal_base"); pct = S("commission")
        amt = round(base * pct / 100, 3)  # computed ONLY here, never from client input
        ex("update drivers set outstanding=outstanding+? where user_id=?", amt, o["driver_id"])
        bal = one("select outstanding from drivers where user_id=?", o["driver_id"])["outstanding"]
        ex("insert into ledger(at,driver_id,order_id,kind,urgent,base,pct,amount,balance_after) values(?,?,?,?,?,?,?,?,?)",
           now(), o["driver_id"], o["id"], "COMMISSION", o["urgent"], base, pct, amt, bal)
        if bal >= S("driver_limit"):
            notify(o["driver_id"], "وصلت عهدتك إلى الحد المسموح. يرجى تسوية العهدة لدى الشركة قبل استقبال طلبات جديدة.")
    msg = {"SEARCHING_DRIVER": "جاري البحث عن سائق", "DRIVER_ASSIGNED": "تم تعيين السائق", "DRIVER_ON_THE_WAY": "السائق قبل الطلب وفي الطريق",
           "DRIVER_ARRIVED": "السائق وصل", "ORDER_PICKED_UP": "تم استلام الطلب", "ON_THE_WAY_TO_CUSTOMER": "الطلب في الطريق",
           "DELIVERED": "تم التسليم", "CANCELLED": "تم إلغاء الطلب"}.get(st)
    if msg: notify(o["customer_id"], f"#{o['id']}: {msg}", order_id=o["id"], kind="status")


def order_view(o, viewer):
    o = dict(o)
    o["history"] = q("select status,at from order_status_history where order_id=? order by id", o["id"])
    o["driver"] = None
    if o["driver_id"]:
        o["driver"] = one("""select u.name,u.phone,u.photo,d.car,d.model,d.year,d.color,d.plate,
            case when d.rating_n>0 then round(1.0*d.rating_sum/d.rating_n,2) end rating
            from users u join drivers d on d.user_id=u.id where u.id=?""", o["driver_id"])
    if viewer and viewer.get("role") == "DRIVER" and o["status"] in ("DELIVERED", "CANCELLED"): o["contact"] = None
    return o


ROUTES = []
def R(m, p, role):
    def deco(f): ROUTES.append((m, re.compile("^" + p + "$"), role, f)); return f
    return deco


@R("POST", "/api/register", None)
def register(u, b):
    need(b, "name", "phone", "password")
    if len(b["password"]) < 8 or not re.fullmatch(r"\+?\d{9,15}", b["phone"]): raise Err(400, "invalid phone/password")
    try: c = ex("insert into users(role,name,phone,pw) values('CUSTOMER',?,?,?)", b["name"], b["phone"], hpw(b["password"]))
    except sqlite3.IntegrityError: raise Err(409, "phone exists")
    return {"id": c.lastrowid}


@R("POST", "/api/register/store", None)
def register_store(u, b):
    need(b, "store_name", "manager_name", "phone", "address", "activity_type", "password")
    f = {k: str(b[k]).strip() for k in ("store_name", "manager_name", "phone", "address", "activity_type")}; pw = str(b["password"])
    if len(pw) < 8 or not re.fullmatch(r"\+?\d{9,15}", f["phone"]): raise Err(400, "invalid phone/password")
    if any(not 2 <= len(f[k]) <= 120 for k in ("store_name", "manager_name", "address", "activity_type")): raise Err(400, "invalid data")
    try: c = ex("insert into users(role,name,phone,pw) values('STORE',?,?,?)", f["store_name"], f["phone"], hpw(pw))  # role is fixed here, never taken from the request
    except sqlite3.IntegrityError: raise Err(409, "phone exists")
    ex("insert into stores(user_id,store_name,manager_name,address,activity_type) values(?,?,?,?,?)", c.lastrowid, f["store_name"], f["manager_name"], f["address"], f["activity_type"])
    audit(c.lastrowid, "register_store", {"id": c.lastrowid}); return {"id": c.lastrowid}


@R("POST", "/api/login", None)
def login(u, b):
    need(b, "phone", "password")
    k = str(b["phone"]); FAILS[k] = [t for t in FAILS.get(k, []) if t > now() - 900]
    if len(FAILS[k]) >= 5: raise Err(429, "too many attempts")
    r = one("select * from users where phone=?", b["phone"])
    if not r or not r["active"] or not chk(b["password"], r["pw"]):
        FAILS[k].append(now()); raise Err(401, "bad credentials")
    FAILS.pop(k, None)
    t = secrets.token_hex(32); ex("insert into sessions values(?,?,?)", t, r["id"], now() + 7 * 86400)
    return {"token": t, "role": r["role"], "name": r["name"]}


@R("GET", "/api/me", "ANY")
def me(u, b):
    r = {k: u[k] for k in ("id", "role", "name", "phone")}
    if u["role"] == "DRIVER":
        dd = one("select available,outstanding,blocked_until,lat,lng,loc_at from drivers where user_id=?", u["id"])
        dd["active_orders"] = one("select count(*) c from orders where driver_id=? and status not in " + OPEN, u["id"])["c"]
        dd["status"] = "UNAVAILABLE" if not dd["available"] else ("BUSY" if dd["active_orders"] >= S("max_active_orders") else "AVAILABLE"); r["driver"] = dd
    if u["role"] == "STORE": r["store"] = one("select store_name,manager_name,address,activity_type,lat,lng from stores where user_id=?", u["id"])
    return r


@R("GET", "/api/services", "ANY")
def services(u, b): return q("select id,name from services where active=1")


@R("GET", "/api/notifications", "ANY")
def notifs(u, b): return q("select * from notifications where user_id=? order by id desc limit 50", u["id"])


@R("POST", "/api/orders", "CUSTOMER")
def new_order(u, b):
    need(b, "service_id", "pickup", "dropoff", "details")
    if not one("select 1 from services where id=? and active=1", b["service_id"]): raise Err(400, "bad service")
    pla, pln = coord(b, "pickup_lat", "pickup_lng"); dla, dln = coord(b, "dropoff_lat", "dropoff_lng")
    c = ex("insert into orders(customer_id,service_id,pickup,dropoff,details,urgent,status,created,pickup_lat,pickup_lng,dropoff_lat,dropoff_lng) values(?,?,?,?,?,?,?,?,?,?,?,?)",
           u["id"], b["service_id"], b["pickup"], b["dropoff"], b["details"], 1 if b.get("urgent") else 0, "NEW", now(), pla, pln, dla, dln)
    o = one("select * from orders where id=?", c.lastrowid)  # driver_id/price/commission from client are ignored
    hist(o["id"], "NEW", u["id"]); notify(u["id"], f"تم إنشاء الطلب #{o['id']}")
    set_status(o, "SEARCHING_DRIVER", u["id"]); dispatch()
    return {"id": o["id"], "note": "سعر التنفيذ يتم الاتفاق عليه بين العميل والسائق قبل التأكيد"}


@R("GET", "/api/orders", "CUSTOMER")
def my_orders(u, b): return q("select * from orders where customer_id=? order by id desc", u["id"])


def get_order(oid, u):
    o = one("select * from orders where id=?", int(oid))
    if not o or (u["role"] in ("CUSTOMER", "STORE") and o["customer_id"] != u["id"]) or (u["role"] == "DRIVER" and o["driver_id"] != u["id"]):
        raise Err(404, "not found")
    return o


@R("GET", r"/api/orders/(\d+)", "ANY")
def order_get(u, b, oid): return order_view(get_order(oid, u), u)


@R("POST", r"/api/orders/(\d+)/cancel", "CUSTOMER")
def cancel(u, b, oid):
    o = get_order(oid, u)
    if o["status"] in ("ORDER_PICKED_UP", "ON_THE_WAY_TO_CUSTOMER", "DELIVERED", "CANCELLED"): raise Err(409, "cannot cancel now")
    ex("update offers set status='CANCELLED' where order_id=? and status='PENDING'", o["id"])
    if o["driver_id"]: notify(o["driver_id"], f"تم إلغاء الطلب #{o['id']}")
    set_status(o, "CANCELLED", u["id"]); return {"ok": 1}


@R("POST", r"/api/orders/(\d+)/confirm", "CUSTOMER")
def confirm(u, b, oid):
    o = get_order(oid, u)
    if o["status"] != "DELIVERED": raise Err(409, "not delivered")
    ex("update orders set confirmed=1 where id=?", o["id"]); return {"ok": 1}


@R("POST", r"/api/orders/(\d+)/rate", "CUSTOMER")
def rate(u, b, oid):
    o = get_order(oid, u); s = b.get("stars")
    if o["status"] != "DELIVERED" or not isinstance(s, int) or not 1 <= s <= 5: raise Err(400, "invalid")
    try: ex("insert into ratings values(?,?,?,?,?)", o["id"], o["driver_id"], u["id"], s, b.get("comment"))
    except sqlite3.IntegrityError: raise Err(409, "already rated")
    ex("update drivers set rating_sum=rating_sum+?,rating_n=rating_n+1 where user_id=?", s, o["driver_id"]); return {"ok": 1}


# ---- driver ----
@R("POST", "/api/driver/available", "DRIVER")
def avail(u, b):
    ex("update drivers set available=? where user_id=?", 1 if b.get("available") else 0, u["id"]); return {"ok": 1}


@R("GET", "/api/driver/offers", "DRIVER")
def offers(u, b):
    # no coordinates before acceptance: the driver only sees the approximate distance
    return q("""select f.order_id,f.expires,f.distance_m,o.urgent,o.pickup,o.dropoff,o.details,o.kind,o.order_value,o.is_paid,o.delivery_fee,o.notes,
        case when o.kind='STORE' then s.store_name end store_name, case when o.kind='STORE' then s.address end store_address
        from offers f join orders o on o.id=f.order_id left join stores s on s.user_id=o.customer_id
        where f.driver_id=? and f.status='PENDING'""", u["id"])


@R("POST", r"/api/driver/offers/(\d+)/(accept|reject)", "DRIVER")
def offer_act(u, b, oid, act):
    f = one("select * from offers where order_id=? and driver_id=? and status='PENDING' and expires>=?", int(oid), u["id"], now())
    if not f: raise Err(409, "offer not available")
    if act == "reject":
        ex("update offers set status='REJECTED' where id=?", f["id"]); return {"ok": 1}
    o = one("select * from orders where id=?", int(oid)); d = one("select * from drivers where user_id=?", u["id"])
    act = one("select count(*) c from orders where driver_id=? and status not in " + OPEN, u["id"])["c"]
    if d["outstanding"] >= S("driver_limit") or d["blocked_until"] > now() or not d["available"] or act >= S("max_active_orders"):
        raise Err(409, "not eligible")
    if ex("update orders set driver_id=? where id=? and driver_id is null and status='SEARCHING_DRIVER'", u["id"], o["id"]).rowcount == 0:
        raise Err(409, "offer not available")  # first accept wins
    ex("update offers set status='ACCEPTED' where id=?", f["id"])
    ex("update offers set status='CLOSED' where order_id=? and status='PENDING'", o["id"])  # offers close instantly for the others
    if act + 1 >= S("max_active_orders"): ex("delete from offers where driver_id=? and status='PENDING'", u["id"])  # full: other pending offers go to the next nearest
    if b.get("agreed_price") is not None:
        ex("update orders set agreed_price=? where id=?", float(b["agreed_price"]), o["id"])  # records only, never in commission
    set_status(dict(o, driver_id=u["id"]), "DRIVER_ASSIGNED", u["id"]); return {"ok": 1}


@R("GET", "/api/driver/orders", "DRIVER")
def d_orders(u, b):
    # customer / store contact is exposed only while the order is assigned to this driver and still open
    O = "o.status not in ('DELIVERED','CANCELLED')"
    return q(f"""select o.id,o.customer_id,o.service_id,o.pickup,o.dropoff,o.details,o.urgent,o.status,o.driver_id,o.agreed_price,o.created,o.confirmed,o.kind,
        o.order_value,o.is_paid,o.delivery_fee,o.notes,o.pickup_lat,o.pickup_lng,o.dropoff_lat,o.dropoff_lng,
        case when {O} then c.name end customer_name, case when {O} then c.phone end customer_phone,
        case when {O} and o.kind='STORE' then s.address end store_address, case when {O} then o.contact end contact
        from orders o join users c on c.id=o.customer_id left join stores s on s.user_id=o.customer_id where o.driver_id=? order by o.id desc""", u["id"])


@R("POST", r"/api/driver/orders/(\d+)/status", "DRIVER")
def d_status(u, b, oid):
    o = get_order(oid, u); st = b.get("status")
    if o["status"] not in FLOW[:-1] or st not in FLOW or FLOW.index(st) != FLOW.index(o["status"]) + 1: raise Err(409, "invalid transition")
    set_status(o, st, u["id"]); return {"ok": 1}


@R("POST", r"/api/driver/orders/(\d+)/cancel", "DRIVER")
def d_cancel(u, b, oid):
    o = get_order(oid, u)
    if o["status"] in ("ORDER_PICKED_UP", "ON_THE_WAY_TO_CUSTOMER", "DELIVERED", "CANCELLED"): raise Err(409, "cannot cancel now")
    ex("update offers set status='DROPPED' where order_id=? and driver_id=?", o["id"], u["id"])
    ex("update orders set driver_id=null where id=?", o["id"])
    set_status(dict(o, driver_id=None), "SEARCHING_DRIVER", u["id"]); return {"ok": 1}


@R("POST", "/api/driver/handover-request", "DRIVER")
def hand_req(u, b):
    if one("select 1 from cash_handovers where driver_id=? and status='REQUESTED'", u["id"]): raise Err(409, "already requested")
    ex("insert into cash_handovers(driver_id,status,requested) values(?,'REQUESTED',?)", u["id"], now())
    for a in q("select id from users where role='ADMIN'"): notify(a["id"], f"طلب تسوية عهدة من السائق #{u['id']}")
    return {"ok": 1}


@R("GET", "/api/driver/ledger", "DRIVER")
def d_ledger(u, b): return q("select * from ledger where driver_id=? order by id desc", u["id"])


# ---- admin ----
@R("POST", "/api/admin/drivers", "ADMIN")
def mk_driver(u, b):
    need(b, "name", "phone", "password", "car", "model", "year", "color", "plate")
    if len(b["password"]) < 8: raise Err(400, "weak password")
    try: c = ex("insert into users(role,name,phone,pw,photo) values('DRIVER',?,?,?,?)", b["name"], b["phone"], hpw(b["password"]), None)
    except sqlite3.IntegrityError: raise Err(409, "phone exists")
    ex("insert into drivers(user_id,car,model,year,color,plate,docs) values(?,?,?,?,?,?,?)", c.lastrowid, b["car"], b["model"], b["year"], b["color"], b["plate"], b.get("docs"))
    audit(u["id"], "create_driver", {"id": c.lastrowid}); return {"id": c.lastrowid}


@R("GET", "/api/admin/drivers", "ADMIN")
def list_drivers(u, b):
    return q("select u.id,u.name,u.phone,u.active,u.photo,d.* from users u join drivers d on d.user_id=u.id")


@R("PATCH", r"/api/admin/drivers/(\d+)", "ADMIN")
def patch_driver(u, b, did):
    if "active" in b: ex("update users set active=? where id=? and role='DRIVER'", 1 if b["active"] else 0, int(did))
    for k in ("car", "model", "year", "color", "plate"):
        if k in b: ex(f"update drivers set {k}=? where user_id=?", b[k], int(did))
    audit(u["id"], "patch_driver", {"id": did, **b}); return {"ok": 1}


@R("GET", "/api/admin/orders", "ADMIN")
def a_orders(u, b): return q("select * from orders order by id desc")


@R("POST", r"/api/admin/orders/(\d+)/assign", "ADMIN")
def a_assign(u, b, oid):
    o = one("select * from orders where id=?", int(oid)); need(b, "driver_id")
    if not o or o["status"] in ("ORDER_PICKED_UP", "ON_THE_WAY_TO_CUSTOMER", "DELIVERED", "CANCELLED"): raise Err(409, "cannot assign")
    if not one("select 1 from users where id=? and role='DRIVER' and active=1", b["driver_id"]): raise Err(400, "bad driver")
    if o["driver_id"]: notify(o["driver_id"], f"تم إلغاء الطلب #{o['id']}")
    ex("update offers set status='CANCELLED' where order_id=? and status='PENDING'", o["id"])
    ex("update orders set driver_id=? where id=?", b["driver_id"], o["id"])
    set_status(dict(o, driver_id=b["driver_id"]), "DRIVER_ASSIGNED", u["id"]); notify(b["driver_id"], f"تم تعيينك للطلب #{o['id']}")
    audit(u["id"], "assign", {"order": o["id"], "driver": b["driver_id"]}); return {"ok": 1}


@R("POST", r"/api/admin/orders/(\d+)/cancel", "ADMIN")
def a_cancel(u, b, oid):
    o = one("select * from orders where id=?", int(oid))
    if not o or o["status"] in ("DELIVERED", "CANCELLED"): raise Err(409, "cannot cancel")
    ex("update offers set status='CANCELLED' where order_id=? and status='PENDING'", o["id"])
    set_status(o, "CANCELLED", u["id"]); audit(u["id"], "admin_cancel", {"order": o["id"]}); return {"ok": 1}


@R("POST", "/api/admin/services", "ADMIN")
def a_svc(u, b):
    need(b, "name"); c = ex("insert into services(name) values(?)", b["name"]); audit(u["id"], "add_service", b); return {"id": c.lastrowid}


@R("PATCH", r"/api/admin/services/(\d+)", "ADMIN")
def a_svc_p(u, b, sid):
    if "name" in b: ex("update services set name=? where id=?", b["name"], int(sid))
    if "active" in b: ex("update services set active=? where id=?", 1 if b["active"] else 0, int(sid))
    audit(u["id"], "patch_service", {"id": sid, **b}); return {"ok": 1}


@R("GET", "/api/admin/settings", "ADMIN")
def g_set(u, b): return {r["k"]: r["v"] for r in q("select * from settings")}


@R("PUT", "/api/admin/settings", "ADMIN")
def p_set(u, b):
    for k, v in b.items():
        if k not in DEFAULTS or not isinstance(v, (int, float)) or v < 0: raise Err(400, f"bad setting {k}")
    for k, v in b.items(): ex("update settings set v=? where k=?", v, k)
    audit(u["id"], "settings", b); return {"ok": 1}


@R("GET", "/api/admin/handovers", "ADMIN")
def g_hand(u, b): return q("select * from cash_handovers order by id desc")


@R("POST", r"/api/admin/handovers/(\d+)/confirm", "ADMIN")
def hand_ok(u, b, hid):
    h = one("select * from cash_handovers where id=? and status='REQUESTED'", int(hid))
    if not h: raise Err(404, "no pending request")
    bal = one("select outstanding from drivers where user_id=?", h["driver_id"])["outstanding"]
    ex("update drivers set outstanding=0 where user_id=?", h["driver_id"])
    ex("update cash_handovers set status='CONFIRMED',amount=?,confirmed_at=?,admin_id=? where id=?", bal, now(), u["id"], h["id"])
    ex("insert into ledger(at,driver_id,kind,amount,balance_after,admin_id) values(?,?,?,?,0,?)", now(), h["driver_id"], "HANDOVER", -bal, u["id"])
    audit(u["id"], "confirm_handover", {"handover": h["id"], "amount": bal}); notify(h["driver_id"], "تم تأكيد استلام العهدة")
    return {"ok": 1, "amount": bal}


@R("GET", "/api/admin/ledger", "ADMIN")
def g_led(u, b): return q("select * from ledger order by id desc")


@R("GET", "/api/admin/stats", "ADMIN")
def stats(u, b):
    c = lambda s, *a: list(one(s, *a).values())[0]
    return {"customers": c("select count(*) from users where role='CUSTOMER'"), "drivers": c("select count(*) from drivers"),
            "available": c("select count(*) from drivers where available=1"),
            "active_orders": c("select count(*) from orders where status not in " + OPEN),
            "urgent": c("select count(*) from orders where urgent=1"), "normal": c("select count(*) from orders where urgent=0"),
            "delivered": c("select count(*) from orders where status='DELIVERED'"), "cancelled": c("select count(*) from orders where status='CANCELLED'"),
            "commissions_total": c("select coalesce(sum(amount),0) from ledger where kind='COMMISSION'"),
            "outstanding_total": c("select coalesce(sum(outstanding),0) from drivers"),
            "at_limit": c("select count(*) from drivers where outstanding>=?", S("driver_limit")),
            "blocked_drivers": c("select count(*) from drivers where blocked_until>?", now()), "fines_total": c("select coalesce(sum(fine),0) from violations where status='ACTIVE'"), "handover_requests": c("select count(*) from cash_handovers where status='REQUESTED'")}


@R("GET", "/api/admin/customers", "ADMIN")
def a_cust(u, b): return q("select id,name,phone,active from users where role='CUSTOMER' order by id desc")


@R("GET", "/api/admin/services", "ADMIN")
def a_svcs(u, b): return q("select * from services")


@R("POST", "/api/devices/register", "ANY")
def dev_reg(u, b):
    t = str(b.get("token", ""))
    if not 20 <= len(t) <= 4096: raise Err(400, "bad token")
    ex("insert or replace into fcm_tokens values(?,?,?)", t, u["id"], now()); return {"ok": 1}  # same device, new account -> token moves


@R("POST", "/api/devices/unregister", "ANY")
def dev_unreg(u, b): ex("delete from fcm_tokens where token=? and user_id=?", str(b.get("token", "")), u["id"]); return {"ok": 1}


def money(v):
    try: x = float(v)
    except (TypeError, ValueError): raise Err(400, "invalid data")
    if not 0 <= x <= 100000: raise Err(400, "invalid data")
    return x


@R("POST", "/api/driver/location", "DRIVER")
def d_loc(u, b):  # a driver can only ever update his own position
    la, ln = coord(b, "lat", "lng")
    if la is None: raise Err(400, "bad coordinates")
    ex("update drivers set lat=?,lng=?,loc_at=? where user_id=?", la, ln, now(), u["id"]); return {"ok": 1}


@R("GET", "/api/store/config", "STORE")
def st_cfg(u, b):
    s_ = one("select lat,lng from stores where user_id=?", u["id"]); return {"fee_normal": S("store_fee_normal"), "fee_urgent": S("store_fee_urgent"), "lat": s_["lat"], "lng": s_["lng"]}


@R("PATCH", "/api/store/location", "STORE")
def st_loc(u, b):
    la, ln = coord(b, "lat", "lng")
    if la is None: raise Err(400, "bad coordinates")
    ex("update stores set lat=?,lng=? where user_id=?", la, ln, u["id"]); return {"ok": 1}


@R("POST", "/api/store/orders", "STORE")
def st_order(u, b):
    need(b, "contact", "dropoff", "details")
    s_ = one("select * from stores where user_id=?", u["id"]); urgent = 1 if b.get("urgent") else 0; paid = 1 if b.get("is_paid") else 0
    value = 0.0 if paid else money(b.get("order_value"))
    pla, pln = coord(b, "pickup_lat", "pickup_lng")
    if pla is None: pla, pln = s_["lat"], s_["lng"]  # default pickup = the store's saved location
    dla, dln = coord(b, "dropoff_lat", "dropoff_lng"); fee = S("store_fee_urgent" if urgent else "store_fee_normal")
    oid = ex("insert into orders(customer_id,service_id,pickup,dropoff,details,urgent,status,created,kind,contact,order_value,is_paid,delivery_fee,notes,pickup_lat,pickup_lng,dropoff_lat,dropoff_lng) values(?,NULL,?,?,?,?,'NEW',?,'STORE',?,?,?,?,?,?,?,?,?)",
             u["id"], str(b.get("pickup") or s_["address"])[:200], str(b["dropoff"])[:200], str(b["details"])[:500], urgent, now(), str(b["contact"])[:120], value, paid, fee, str(b.get("notes") or "")[:500], pla, pln, dla, dln).lastrowid
    o = one("select * from orders where id=?", oid); hist(oid, "NEW", u["id"]); notify(u["id"], f"تم إنشاء الطلب #{oid}")
    set_status(o, "SEARCHING_DRIVER", u["id"]); dispatch(); return {"id": oid, "delivery_fee": fee}


@R("GET", "/api/store/orders", "STORE")
def st_list(u, b):
    return q("select id,pickup,dropoff,details,urgent,status,order_value,is_paid,delivery_fee,notes,contact,created from orders where customer_id=? and kind='STORE' order by id desc", u["id"])


@R("POST", r"/api/store/orders/(\d+)/cancel", "STORE")
def st_cancel(u, b, oid): return cancel(u, b, oid)


SUPPORT = {"phone": os.environ.get("SUPPORT_PHONE", ""), "whatsapp": os.environ.get("SUPPORT_WHATSAPP", "")}


@R("GET", "/api/support", "ANY")
def support(u, b): return SUPPORT


@R("POST", "/api/support/report", "ANY")
def s_report(u, b):
    need(b, "message"); msg = str(b["message"]).strip()[:1000]
    if len(msg) < 5: raise Err(400, "invalid data")
    try: oid = int(b["order_id"]) if b.get("order_id") not in (None, "") else None
    except (TypeError, ValueError): raise Err(400, "invalid data")
    ex("insert into reports(user_id,order_id,message,created,status) values(?,?,?,?,'OPEN')", u["id"], oid, msg, now())
    for a in q("select id from users where role='ADMIN'"): notify(a["id"], f"بلاغ جديد من {u['name']}")
    return {"ok": 1}


@R("GET", "/api/admin/reports", "ADMIN")
def a_reports(u, b): return q("select r.*,u.name user_name,u.role user_role,u.phone user_phone from reports r join users u on u.id=r.user_id order by r.id desc limit 200")


@R("POST", r"/api/admin/reports/(\d+)/resolve", "ADMIN")
def a_report_ok(u, b, rid): ex("update reports set status='DONE' where id=?", int(rid)); audit(u["id"], "resolve_report", {"id": rid}); return {"ok": 1}


@R("GET", "/api/push/key", "DRIVER")
def p_key(u, b): return {"key": VAPID_PUB}


@R("POST", "/api/push/subscribe", "DRIVER")
def p_sub(u, b):
    ep = str(b.get("endpoint", "")); h = urllib.parse.urlparse(ep).hostname or ""
    if not ep.startswith("https://") or len(ep) > 600 or not any(h == a or h.endswith("." + a) for a in PUSH_HOSTS): raise Err(400, "bad endpoint")
    ex("insert or replace into push_subs values(?,?,?)", ep, u["id"], now()); return {"ok": 1}


@R("POST", "/api/push/unsubscribe", "DRIVER")
def p_unsub(u, b): ex("delete from push_subs where endpoint=? and user_id=?", str(b.get("endpoint", "")), u["id"]); return {"ok": 1}


@R("POST", r"/api/admin/drivers/(\d+)/photo", "ADMIN")
def a_photo(u, b, did):
    im = str(b.get("image", ""))
    m = re.fullmatch(r"data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)", im)
    if not m or len(im) > 90000: raise Err(400, "bad image")
    try: raw = base64.b64decode(m.group(2), validate=True)
    except Exception: raise Err(400, "bad image")
    if not (raw[:3] == b"\xff\xd8\xff" or raw[:8] == b"\x89PNG\r\n\x1a\n" or (raw[:4] == b"RIFF" and raw[8:12] == b"WEBP")): raise Err(400, "bad image")
    if not one("select 1 from users where id=? and role='DRIVER'", int(did)): raise Err(404, "not found")
    ex("update users set photo=? where id=?", im, int(did)); audit(u["id"], "set_driver_photo", {"id": did}); return {"ok": 1}


@R("POST", r"/api/admin/drivers/(\d+)/violations", "ADMIN")
def a_viol(u, b, did):
    need(b, "reason"); d = one("select * from drivers where user_id=?", int(did))
    if not d: raise Err(404, "not found")
    oid = b.get("order_id")
    if oid and not one("select 1 from orders where id=?", int(oid)): raise Err(400, "bad order")
    fine = S("violation_fine"); hrs = S("violation_block_hours"); until = max(d["blocked_until"], now() + int(hrs * 3600)); reason = str(b["reason"]).strip()[:300]
    vid = ex("insert into violations(driver_id,order_id,reason,fine,created,blocked_until,status,admin_id) values(?,?,?,?,?,?,'ACTIVE',?)",
             int(did), oid, reason, fine, now(), until, u["id"]).lastrowid
    ex("update drivers set outstanding=outstanding+?,blocked_until=? where user_id=?", fine, until, int(did))
    bal = one("select outstanding from drivers where user_id=?", int(did))["outstanding"]
    ex("insert into ledger(at,driver_id,order_id,kind,amount,balance_after,admin_id,note) values(?,?,?,?,?,?,?,?)", now(), int(did), oid, "FINE", fine, bal, u["id"], reason)
    ex("delete from offers where driver_id=? and status='PENDING'", int(did))
    audit(u["id"], "create_violation", {"id": vid, "driver": did, "order": oid, "fine": fine, "reason": reason})
    notify(int(did), f"تم إيقاف استقبال الطلبات لمدة {hrs:g} ساعة بسبب مخالفة: {reason}. غرامة {fine:g} د.ل"); return {"id": vid}


@R("POST", r"/api/admin/violations/(\d+)/cancel", "ADMIN")
def a_viol_c(u, b, vid):
    need(b, "note"); v = one("select * from violations where id=? and status='ACTIVE'", int(vid))
    if not v: raise Err(409, "not active")
    ex("update violations set status='CANCELLED',cancelled_by=?,cancelled_at=?,cancel_note=? where id=?", u["id"], now(), str(b["note"])[:300], v["id"])
    rest = one("select max(blocked_until) m from violations where driver_id=? and status='ACTIVE'", v["driver_id"])["m"] or 0
    ex("update drivers set outstanding=outstanding-?,blocked_until=? where user_id=?", v["fine"], rest, v["driver_id"])
    bal = one("select outstanding from drivers where user_id=?", v["driver_id"])["outstanding"]
    ex("insert into ledger(at,driver_id,order_id,kind,amount,balance_after,admin_id,note) values(?,?,?,?,?,?,?,?)", now(), v["driver_id"], v["order_id"], "FINE_REVERSAL", -v["fine"], bal, u["id"], str(b["note"])[:300])
    audit(u["id"], "cancel_violation", {"id": v["id"], "note": b["note"]}); notify(v["driver_id"], "تم إلغاء مخالفة من الإدارة وإعادة الغرامة"); return {"ok": 1}


@R("GET", "/api/admin/violations", "ADMIN")
def a_viols(u, b): return q("select v.*,u.name driver_name from violations v join users u on u.id=v.driver_id order by v.id desc")


@R("GET", "/api/driver/violations", "DRIVER")
def d_viols(u, b): return q("select id,order_id,reason,fine,created,blocked_until,status from violations where driver_id=? order by id desc", u["id"])


@R("GET", "/healthz", None)
def health(u, b): return {"ok": 1}


@R("POST", "/api/logout", "ANY")
def logout(u, b): ex("delete from sessions where token=?", u["_tok"]); return {"ok": 1}


@R("PATCH", "/api/me", "ANY")
def upd_me(u, b):
    if b.get("name") and u["role"] == "CUSTOMER": ex("update users set name=? where id=?", str(b["name"]).strip()[:80], u["id"])
    if b.get("new_password"):
        need(b, "old_password")
        if not chk(str(b["old_password"]), u["pw"]) or len(str(b["new_password"])) < 8: raise Err(400, "invalid password")
        ex("update users set pw=? where id=?", hpw(str(b["new_password"])), u["id"])
        ex("delete from sessions where user_id=? and token!=?", u["id"], u["_tok"])
    audit(u["id"], "update_profile", {"password_changed": bool(b.get("new_password"))}); return {"ok": 1}


@R("POST", "/api/notifications/read", "ANY")
def notif_read(u, b): ex("update notifications set read=1 where user_id=?", u["id"]); return {"ok": 1}


@R("PATCH", r"/api/admin/customers/(\d+)", "ADMIN")
def a_cust_p(u, b, cid):
    need(b, "active"); a = 1 if b["active"] else 0
    ex("update users set active=? where id=? and role='CUSTOMER'", a, int(cid))
    if not a: ex("delete from sessions where user_id=?", int(cid))
    audit(u["id"], "set_customer_active", {"id": cid, "active": a}); return {"ok": 1}


@R("POST", r"/api/admin/drivers/(\d+)/password", "ADMIN")
def a_drv_pw(u, b, did):
    need(b, "password")
    if len(str(b["password"])) < 8: raise Err(400, "weak password")
    ex("update users set pw=? where id=? and role='DRIVER'", hpw(str(b["password"])), int(did))
    ex("delete from sessions where user_id=?", int(did)); audit(u["id"], "reset_driver_password", {"id": did}); return {"ok": 1}


@R("GET", "/api/admin/audit", "ADMIN")
def a_audit(u, b): return q("select * from audit_logs order by id desc limit 200")


class H(BaseHTTPRequestHandler):
    def end_headers(s):
        for k, v in SEC: s.send_header(k, v)
        o = s.headers.get("Origin")
        if o and o in ALLOWED_ORIGINS:
            for k, v in (("Access-Control-Allow-Origin", o), ("Vary", "Origin"), ("Access-Control-Allow-Headers", "Authorization, Content-Type"),
                         ("Access-Control-Allow-Methods", "GET, POST, PATCH, PUT, OPTIONS"), ("Access-Control-Max-Age", "600")): s.send_header(k, v)
        super().end_headers()

    def log_message(s, *a): pass

    def handle_any(s):
        try:
            path = s.path.split("?")[0]; user = None
            if s.command == "GET" and path in ("/", "/index.html", "/admin", "/driver", "/sw.js", "/map.js"):
                d = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), {"/admin": "admin.html", "/driver": "driver.html", "/sw.js": "sw.js", "/map.js": "map.js"}.get(path, "index.html")), "rb").read()
                s.send_response(200); s.send_header("Content-Type", "application/javascript" if path in ("/sw.js", "/map.js") else "text/html; charset=utf-8")
                s.send_header("Content-Length", str(len(d))); s.end_headers(); s.wfile.write(d); return
            n = int(s.headers.get("Content-Length") or 0)
            if n > 100000: raise Err(413, "too large")
            b = json.loads(s.rfile.read(n) or b"{}") if n else {}
            if not isinstance(b, dict): raise Err(400, "bad body")
            tok = (s.headers.get("Authorization") or "")[7:]
            se = one("select user_id from sessions where token=? and exp>?", tok, now()) if tok else None
            if se:
                user = one("select * from users where id=? and active=1", se["user_id"])
                if user: user["_tok"] = tok
            for m, rx, role, f in ROUTES:
                mt = rx.match(path)
                if m == s.command and mt:
                    if role and (not user or (role != "ANY" and user["role"] != role)): raise Err(401 if not user else 403, "forbidden")
                    dispatch(); out = f(user, b, *mt.groups()); db.commit(); return s.send(200, out)
            raise Err(404, "not found")
        except Err as e: db.rollback(); s.send(e.code, {"error": e.msg})
        except Exception as e: db.rollback(); s.send(500, {"error": "server error"})

    def send(s, code, obj):
        d = json.dumps(obj, ensure_ascii=False).encode()
        s.send_response(code); s.send_header("Content-Type", "application/json; charset=utf-8")
        s.send_header("Content-Length", str(len(d))); s.end_headers(); s.wfile.write(d)

    def do_OPTIONS(s): s.send_response(204); s.send_header("Content-Length", "0"); s.end_headers()

    do_GET = do_POST = do_PATCH = do_PUT = handle_any


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000)); init(); print(f"Talbista on :{port}"); HTTPServer(("0.0.0.0", port), H).serve_forever()
