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


    def test_mobile_readiness_probe_targets_v1_ai_ready_get(self):
        app = (ROOT / "mobile" / "app.js").read_text(encoding="utf-8")
        self.assertIn('const AI_READY_PATH = C.AI_READY_PATH || "/v1/ai-ready";', app)
        self.assertIn("fetchBounded(base + AI_READY_PATH, {}, remaining)", app)
        self.assertIn('headers: {', app)
        self.assertIn('"X-C33-Deadline-Epoch-Ms"', app)

    def test_bundled_backend_fallback_matches_runtime_backend(self):
        config = (ROOT / "mobile" / "public" / "config.js").read_text(encoding="utf-8")
        app = (ROOT / "mobile" / "app.js").read_text(encoding="utf-8")
        self.assertIn('iac33-backup-production.up.railway.app', config)
        self.assertIn('https://iac33-backup-production.up.railway.app', app)

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

    def test_pagehide_aborts_registered_controllers_and_clears_set(self):
        app = (ROOT / "mobile" / "app.js").read_text(encoding="utf-8")
        self.assertIn('window.addEventListener("pagehide"', app)
        self.assertIn("for (const controller of activeControllers) controller.abort();", app)
        self.assertIn("activeControllers.clear();", app)

    def test_bounded_requests_join_pagehide_cancellation_set(self):
        app = (ROOT / "mobile" / "app.js").read_text(encoding="utf-8")
        self.assertIn("activeControllers.add(controller);", app)
        self.assertIn("activeControllers.delete(controller);", app)

    def test_frontend_backend_requests_disable_http_cache(self):
        app = (ROOT / "mobile" / "app.js").read_text(encoding="utf-8")
        self.assertGreaterEqual(app.count('cache: "no-store"'), 2)
        self.assertIn('"Cache-Control": "no-cache"', app)

    def test_frontend_uses_single_public_runtime_config(self):
        self.assertTrue((ROOT / "mobile" / "public" / "config.js").exists())
        self.assertFalse((ROOT / "mobile" / "config.js").exists())

    def test_frontend_default_timeout_cannot_drift_to_28s(self):
        app = (ROOT / "mobile" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Number(C.CLIENT_TIMEOUT_MS || 22000)", app)
        self.assertNotIn("Number(C.CLIENT_TIMEOUT_MS || 28000)", app)

    def test_mobile_diagnostics_are_bounded_and_truncated(self):
        app = (ROOT / "mobile" / "app.js").read_text(encoding="utf-8")
        self.assertIn("const MAX_DIAGNOSTICS = 40;", app)
        self.assertIn('.slice(0, MAX_DIAGNOSTICS)', app)
        self.assertIn('function truncateDiagnostic(value, max = 4000)', app)
        self.assertIn('"…[truncated]"', app)

    def test_mobile_circuit_state_uses_v4_storage_key(self):
        app = (ROOT / "mobile" / "app.js").read_text(encoding="utf-8")
        self.assertIn('const CIRCUIT_KEY = "C33_BACKEND_CIRCUITS_V4"', app)

    def test_frontend_has_single_connection_probe_at_a_time(self):
        app = (ROOT / "mobile" / "app.js").read_text(encoding="utf-8")
        self.assertIn("let refreshInFlight = null;", app)
        self.assertRegex(app, r"if \(refreshInFlight\) return refreshInFlight;")

    def test_web_sources_are_rendered_as_safe_dom_links(self):
        app = (ROOT / "mobile" / "app.js").read_text(encoding="utf-8")
        self.assertIn('document.createElement("a")', app)
        self.assertIn("link.textContent =", app)
        self.assertIn('link.rel = "noopener noreferrer"', app)
        self.assertIn('messageNode.appendChild(sourceBox)', app)
        self.assertNotIn("sourceBox.innerHTML", app)

    def test_local_fallback_is_explicitly_marked_degraded(self):
        app = (ROOT / "mobile" / "app.js").read_text(encoding="utf-8")
        self.assertIn('provider_used: "local"', app)
        self.assertIn('model: "client-deterministic-fallback"', app)
        self.assertIn('used_local_fallback: true', app)
        self.assertIn('transition("DEGRADED", "NEXO · respaldo local · IA remota no disponible")', app)

    def test_stream_interrupt_recovers_by_request_id_railway_then_deplexo(self):
        app = (ROOT / "mobile" / "app.js").read_text(encoding="utf-8")
        self.assertIn("async function recoverInterruptedStream(", app)
        self.assertIn('"X-C33-Replay-Only": "true"', app)
        self.assertIn('"X-C33-Recovery": "sse-request-id"', app)
        self.assertIn('sequence: "Railway -> Deplexo"', app)
        self.assertIn('recordDiagnostic("stream-replay-railway"', app)
        self.assertIn('recordDiagnostic("stream-replay-deplexo"', app)
        self.assertIn("replayed: Boolean(data?._meta?.replayed)", app)
        self.assertIn("recovery_request_id_mismatch", app)
        self.assertIn('replayHeaders', app)
        self.assertIn('requestPayload?.request_id', app)

    def test_stream_interrupt_uses_same_request_id_for_http_recovery(self):
        app = (ROOT / "mobile" / "app.js").read_text(encoding="utf-8")
        self.assertIn("body: payload", app)
        self.assertIn("const payload = JSON.stringify({ ...requestPayload, stream: false });", app)
        self.assertIn("const requestId = String(requestPayload?.request_id || \"\").trim();", app)
        self.assertIn('request_id: requestId', app)

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
        workflows = ("build-apk.yml", "c33-certification.yml")
        for name in workflows:
            workflow = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            self.assertIn('versionCode 6', workflow)
            self.assertIn('versionName "0.1.6"', workflow)
            self.assertNotIn("0.1.4", workflow)

if __name__ == "__main__":
    unittest.main()
