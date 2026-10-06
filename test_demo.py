import os, sys, json, shutil, subprocess, tempfile, threading, functools, http.server
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); M = os.path.join(HERE, "mobile")
# --- build outputs and native assets ---
assert subprocess.run(["python3", "demo/build_preview.py"], cwd=M, capture_output=True).returncode == 0
assert subprocess.run(["python3", "build_www.py"], cwd=M, env={**os.environ, "DEMO": "1"}, capture_output=True).returncode == 0
assert all(os.path.exists(f"{M}/www/{f}") for f in ("app.html", "customer.html", "driver.html", "admin.html", "demo-mock.js"))
assert "native.js" not in open(f"{M}/www/customer.html", encoding="utf-8").read() and "window.TB_API=" not in open(f"{M}/www/driver.html", encoding="utf-8").read()
for f in (HERE + "/demo/talbista-demo.html", M + "/demo/demo-mock.js", M + "/app_demo.html", M + "/demo/build_preview.py"): assert "watchposition" not in open(f, encoding="utf-8").read().lower()
R = M + "/overlay/res"
for n, s in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items(): assert Image.open(f"{R}/mipmap-{n}/ic_launcher.png").size == (s, s) and Image.open(f"{R}/mipmap-{n}/ic_launcher_foreground.png").size == (s * 9 // 4,) * 2
assert Image.open(f"{R}/drawable-port-xxhdpi/splash.png").size == (960, 1600) and "0B7A55" in open(f"{R}/values/ic_launcher_background.xml").read()
T = tempfile.mkdtemp(); man = f"{T}/android/app/src/main"; os.makedirs(f"{man}/res/drawable-port-hdpi"); open(f"{man}/res/drawable-port-hdpi/splash.png", "w").write("old"); open(f"{man}/res/drawable-port-hdpi/capacitor_default.png", "w").write("keep")
open(f"{man}/AndroidManifest.xml", "w").write('<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n    <application android:label="x">\n    </application>\n</manifest>\n')
assert subprocess.run(["python3", "apply_android_overlay.py", f"{T}/android"], cwd=M, env={**os.environ, "ALLOW_NO_FIREBASE": "1"}, capture_output=True).returncode == 0
assert Image.open(f"{man}/res/drawable-port-hdpi/splash.png").size == (480, 800) and os.path.exists(f"{man}/res/mipmap-xxxhdpi/ic_launcher_round.png")
# --- real browser run at phone size (skipped if Chromium is not available) ---
CH = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
try:
    from playwright.sync_api import sync_playwright
    assert os.path.exists(CH)
except Exception: print("DEMO OK (browser checks skipped: Chromium/Playwright unavailable)"); sys.exit(0)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8791), functools.partial(http.server.SimpleHTTPRequestHandler, directory=HERE + "/demo" if False else HERE)); threading.Thread(target=srv.serve_forever, daemon=True).start()
srv2 = http.server.ThreadingHTTPServer(("127.0.0.1", 8792), functools.partial(http.server.SimpleHTTPRequestHandler, directory=M + "/www")); threading.Thread(target=srv2.serve_forever, daemon=True).start()
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CH, args=["--no-sandbox"]); pg = b.new_context(viewport={"width": 390, "height": 844}, locale="ar", is_mobile=True, has_touch=True).new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:8791/demo/talbista-demo.html"); fr = pg.frame_locator("#f")
    fr.locator("#new").wait_for(); fr.locator("#new").click(); fr.locator("#sv").wait_for(); fr.locator("#pk").fill("أ"); fr.locator("#dr").fill("ب"); fr.locator("#dt").fill("ج"); fr.locator(".seg label.ur").click(); fr.locator("#ok").click()
    fr.locator(".tl").wait_for(); assert "مستعجل" in fr.locator(".card").first.inner_text()
    pg.click("[data-k=store]"); fr.locator("#so").wait_for(); assert "متجر الأمل" in fr.locator("main").inner_text()
    pg.click("[data-k=driver]"); fr.locator("[data-a=ac]").wait_for(); pg.click("[data-k=admin]"); fr.locator(".grid").wait_for(); assert "السائقون" in fr.locator(".grid").inner_text()
    pg.goto("http://127.0.0.1:8792/app.html"); pg.wait_for_timeout(2300); pg.click("#c"); pg.wait_for_selector("#new")
    for k in ("#d", "#a"):
        pg.goto("http://127.0.0.1:8792/app.html?choose=1"); pg.wait_for_timeout(300); pg.click(k); pg.wait_for_timeout(1000)
    assert errs == [], errs; b.close()
print("DEMO OK")
