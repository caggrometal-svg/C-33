import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class MobileContractTests(unittest.TestCase):
    def test_single_runtime_config_is_railway_only_and_uses_22s(self):
        config = (ROOT / "mobile" / "config.js").read_text(encoding="utf-8")
        self.assertIn("iac33-backup-production.up.railway.app", config)
        self.assertNotIn("onrender.com", config)
        self.assertEqual(config.count("BACKEND_URLS:"), 1)
        self.assertIn("CLIENT_TIMEOUT_MS: 22000", config)
        self.assertIn("READY_PATH: "/ready"", config)
        self.assertIn("AI_READY_PATH: "/v1/ai-ready"", config)

    def test_conflicting_public_runtime_config_is_absent(self):
        self.assertFalse((ROOT / "mobile" / "public" / "config.js").exists())

    def test_frontend_default_timeout_cannot_drift_to_28s(self):
        app = (ROOT / "mobile" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Number(C.CLIENT_TIMEOUT_MS || 22000)", app)
        self.assertNotIn("Number(C.CLIENT_TIMEOUT_MS || 28000)", app)

    def test_frontend_has_single_connection_probe_at_a_time(self):
        app = (ROOT / "mobile" / "app.js").read_text(encoding="utf-8")
        self.assertIn("let refreshInFlight = null;", app)
        self.assertRegex(app, r"if \(refreshInFlight\) return refreshInFlight;")

if __name__ == "__main__":
    unittest.main()
