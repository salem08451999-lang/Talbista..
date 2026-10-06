#!/bin/sh
# Builds a debug APK. Requires: Node 20, JDK 17, Android SDK, google-services.json, SERVER_URL=https://...
set -e
cd "$(dirname "$0")"
[ "$DEMO" = "1" ] && export ALLOW_NO_FIREBASE=1
[ "$DEMO" = "1" ] || [ -n "$SERVER_URL" ] || { echo "SERVER_URL (https://...) is required"; exit 1; }
npm install
python3 build_www.py
[ -d android ] || npx cap add android
python3 apply_android_overlay.py android
npx cap sync android
cd android && chmod +x gradlew && ./gradlew assembleDebug
echo "APK: $(pwd)/app/build/outputs/apk/debug/app-debug.apk"
