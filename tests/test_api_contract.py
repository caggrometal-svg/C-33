from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self.api = (ROOT / "src" / "api.py").read_text(encoding="utf-8")
        self.providers = (ROOT / "src" / "resilience" / "providers.py").read_text(encoding="utf-8")

    def test_stream_replays_completed_request_by_id(self):
        self.assertIn("existing_assistant_for_request(payload.conversation_id, request_id)", self.api)
        self.assertIn('"replayed"] = True', self.api)
        self.assertIn('"meta":final_meta', self.api)

    def test_generation_endpoints_are_rate_limited(self):
        self.assertIn('_enforce_rate_limit(request, "generation", _RATE_LIMIT_GENERATION)', self.api)
        self.assertIn('_enforce_rate_limit(request, "ai-ready", _RATE_LIMIT_AI_READY)', self.api)

    def test_ai_readiness_cache_is_bounded(self):
        self.assertNotIn("time.monotonic() + 120.0", self.api)
        self.assertIn("time.monotonic() + 5.0", self.api)

    def test_http_and_stream_transport_errors_use_nested_context(self):
        self.assertGreaterEqual(self.providers.count("cause = exc.__cause__"), 2)
        self.assertGreaterEqual(self.providers.count("temporary failure in name resolution"), 2)

if __name__ == "__main__":
    unittest.main()
