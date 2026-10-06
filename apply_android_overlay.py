"""Applies Talbista native customizations to the generated Capacitor android/ project (idempotent)."""
import os, sys, shutil
H = os.path.dirname(os.path.abspath(__file__)); A = sys.argv[1] if len(sys.argv) > 1 else "android"
GS = os.environ.get("GOOGLE_SERVICES_JSON_PATH", "google-services.json"); main = os.path.join(A, "app", "src", "main")
if not os.path.isdir(main): sys.exit("android project not found: run `npx cap add android` first")
d = os.path.join(main, "java", "ly", "talbista", "app"); os.makedirs(d, exist_ok=True); shutil.copy(os.path.join(H, "overlay", "MainActivity.java"), d)
res = os.path.join(main, "res")
for root, _, files in os.walk(res):  # drop Capacitor's default splash images; ours are copied below
    for f in files:
        if f == "splash.png": os.remove(os.path.join(root, f))
shutil.copytree(os.path.join(H, "overlay", "res"), res, dirs_exist_ok=True)  # sounds, icons, splash, launcher colour
if os.path.isfile(GS): shutil.copy(GS, os.path.join(A, "app", "google-services.json"))
elif os.environ.get("ALLOW_NO_FIREBASE") != "1": sys.exit("google-services.json is required for push notifications (Firebase console)")
mp = os.path.join(main, "AndroidManifest.xml"); s = open(mp, encoding="utf-8").read()
for perm in ("POST_NOTIFICATIONS", "VIBRATE", "ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION"):
    if f"android.permission.{perm}" not in s: s = s.replace("<application", f'<uses-permission android:name="android.permission.{perm}" />\n    <application', 1)
if "default_notification_channel_id" not in s:
    s = s.replace("</application>", '    <meta-data android:name="com.google.firebase.messaging.default_notification_channel_id" android:value="talbista_default" />\n    </application>', 1)
if os.environ.get("ALLOW_CLEARTEXT") == "1" and "usesCleartextTraffic" not in s: s = s.replace("<application", '<application android:usesCleartextTraffic="true"', 1)
open(mp, "w", encoding="utf-8").write(s); print("overlay applied to", A)
