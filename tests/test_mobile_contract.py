from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class MobileContractTests(unittest.TestCase):
    def test_mobile_package_and_android_release_target_are_on_0_1_6(self):
        package = (ROOT / "mobile" / "package.json").read_text(encoding="utf-8")
        self.assertIn('"version": "0.1.6"', package)

    def test_single_runtime_config_is_railway_only_and_uses_22s(self):
        config = (ROOT / "mobile" / "public" / "config.js").read_text(encoding="utf-8")
        self.assertIn("iac33-backup-production.up.railway.app", config)
        self.assertNotIn("onrender.com", config)
        self.assertEqual(config.count("BACKEND_URLS:"), 1)
        self.assertIn("CLIENT_TIMEOUT_MS: 22000", config)
        self.assertIn('READY_PATH: "/ready"', config)
        self.assertIn('AI_READY_PATH: "/v1/ai-ready"', config)


    def test_mobile_runtime_config_has_safe_operational_bounds(self):
        config = (ROOT / "mobile" / "public" / "config.js").read_text(encoding="utf-8")
        self.assertIn("PROBE_TIMEOUT_MS: 4000", config)
        self.assertIn("CIRCUIT_COOLDOWN_MS: 10000", config)
        self.assertIn("CIRCUIT_FAILURE_THRESHOLD: 2", config)
        self.assertNotIn('http://', config)

    def test_stream_allows_server_fallback_and_has_http_recovery(self):
        app = (ROOT / "mobile" / "app.js").read_text(encoding="utf-8")
        self.assertIn('"X-C33-Allow-Local-Fallback": "true"', app)
        self.assertIn('stream-http-recovery', app)
        self.assertIn('stream-http-recovery-failed', app)
        self.assertIn('requestWithFailover(API_PATH', app)
        self.assertIn('client-local-fallback', app)
        self.assertIn('client-deterministic-fallback', app)
        self.assertIn('used_local_fallback', app)

    def test_frontend_uses_single_public_runtime_config(self):
        self.assertTrue((ROOT / "mobile" / "public" / "config.js").exists())
        self.assertFalse((ROOT / "mobile" / "config.js").exists())

    def test_frontend_default_timeout_cannot_drift_to_28s(self):
        app = (ROOT / "mobile" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Number(C.CLIENT_TIMEOUT_MS || 22000)", app)
        self.assertNotIn("Number(C.CLIENT_TIMEOUT_MS || 28000)", app)

    def test_frontend_has_single_connection_probe_at_a_time(self):
        app = (ROOT / "mobile" / "app.js").read_text(encoding="utf-8")
        self.assertIn("let refreshInFlight = null;", app)
        self.assertRegex(app, r"if \(refreshInFlight\) return refreshInFlight;")

    def test_frontend_consumes_structured_sse_error_events(self):
        app = (ROOT / "mobile" / "app.js").read_text(encoding="utf-8")
        self.assertIn('if (eventName === "error")', app)
        self.assertIn('streamError = [statusHint, data?.reason || "stream_error"', app)
        self.assertIn('finalMeta = data?._meta || finalMeta', app)

    def test_frontend_pauses_readiness_probes_during_stream(self):
        app = (ROOT / "mobile" / "app.js").read_text(encoding="utf-8")
        self.assertIn("activeControllers.size > 0", app)
        self.assertIn("activeControllers.size === 0", app)

    def test_all_apk_workflows_pin_nexo_0_1_6_version(self):
        workflows = (
            "android-apk.yml",
            "build-apk.yml",
            "nexo-android.yml",
            "c33-certification.yml",
        )
        for name in workflows:
            workflow = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            self.assertIn('versionCode 6', workflow)
            self.assertIn('versionName "0.1.6"', workflow)
            self.assertNotIn("0.1.4", workflow)

if __name__ == "__main__":
    unittest.main()
