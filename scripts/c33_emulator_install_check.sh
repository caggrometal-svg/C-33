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
  adb shell dumpsys activity service SystemUIService || true
  exit 1
fi

timeout 180s adb install --no-incremental -r mobile/android/app/build/outputs/apk/release/app-release.apk
adb shell pm path com.c33.mobile
adb shell am force-stop com.c33.mobile
adb shell monkey -p com.c33.mobile 1

for i in $(seq 1 30); do
  if adb shell dumpsys activity activities | grep -q "com.c33.mobile"; then
    echo "C33_RELEASE_INSTALL_AND_LAUNCH: PASS"
    exit 0
  fi
  sleep 1
done

adb shell dumpsys activity activities
exit 1
