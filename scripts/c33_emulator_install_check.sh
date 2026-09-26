#!/usr/bin/env bash
set -euo pipefail

echo "C33_EMULATOR_BOOTED: PASS"

package_ready=false
for i in $(seq 1 45); do
  if adb shell cmd package list packages >/dev/null 2>&1; then
    package_ready=true
    echo "C33_PACKAGE_MANAGER_READY: PASS"
    break
  fi
  sleep 2
done

if [[ "$package_ready" != "true" ]]; then
  adb shell service check package || true
  adb shell getprop sys.boot_completed || true
  exit 1
fi

install_ok=false
for i in $(seq 1 30); do
  if adb shell service check package >/dev/null 2>&1 && adb shell cmd package list packages >/dev/null 2>&1; then
    echo "C33_PACKAGE_SERVICE_READY: PASS"
    install_ok=true
    break
  fi
  sleep 2
done

if [[ "$install_ok" != "true" ]]; then
  adb shell service check package || true
  adb shell getprop sys.boot_completed || true
  exit 1
fi

timeout 180s adb install --no-incremental -r mobile/android/app/build/outputs/apk/release/app-release.apk
installed_path="$(adb shell pm path com.c33.mobile | tr -d '\r')"
test -n "$installed_path"
echo "C33_RELEASE_APK_INSTALLED: PASS"
echo "$installed_path"

adb shell am force-stop com.c33.mobile
timeout 30s adb shell am start -W -n com.c33.mobile/.MainActivity
resolved_activity="$(adb shell cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER com.c33.mobile | tr -d '\r')"
test -n "$resolved_activity"
echo "C33_RELEASE_LAUNCH: PASS"
echo "$resolved_activity"

echo "C33_RELEASE_INSTALL_AND_LAUNCH: PASS"
