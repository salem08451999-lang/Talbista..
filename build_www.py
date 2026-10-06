"""Builds www/ (bundled UI) from the web pages. SERVER_URL must be the HTTPS backend address."""
import os, sys, json, shutil
H = os.path.dirname(os.path.abspath(__file__)); SRC = os.path.dirname(H); OUT = os.path.join(H, "www")
DEMO = os.environ.get("DEMO") == "1"
url = os.environ.get("SERVER_URL", "").rstrip("/")
if DEMO:
    shutil.rmtree(OUT, ignore_errors=True); os.makedirs(OUT)
    inj = '<script src="demo-mock.js"></script></head>'
    for src, dst in (("index.html", "customer.html"), ("driver.html", "driver.html"), ("admin.html", "admin.html")):
        s = open(os.path.join(SRC, src), encoding="utf-8").read(); open(os.path.join(OUT, dst), "w", encoding="utf-8").write(s.replace("</head>", inj, 1))
    shutil.copy(os.path.join(SRC, "map.js"), OUT); shutil.copy(os.path.join(H, "app_demo.html"), os.path.join(OUT, "app.html")); shutil.copy(os.path.join(H, "demo", "demo-mock.js"), OUT)
    print("DEMO www built (no server)"); sys.exit(0)
if not url.startswith("https://") and not (os.environ.get("ALLOW_CLEARTEXT") == "1" and url.startswith("http://")):
    sys.exit("SERVER_URL must be an https:// address (Android blocks plain http)")
shutil.rmtree(OUT, ignore_errors=True); os.makedirs(OUT)
inject = f'<script>window.TB_API={json.dumps(url)}</script><script src="native.js"></script></head>'
for src, dst in (("index.html", "customer.html"), ("driver.html", "driver.html")):
    s = open(os.path.join(SRC, src), encoding="utf-8").read(); assert "</head>" in s
    open(os.path.join(OUT, dst), "w", encoding="utf-8").write(s.replace("</head>", inject, 1))
for f in ("app.html", "native.js"): shutil.copy(os.path.join(H, f), OUT)
shutil.copy(os.path.join(SRC, "map.js"), OUT)
print("www built for", url)
