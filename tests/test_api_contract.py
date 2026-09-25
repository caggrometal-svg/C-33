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

    def test_ai_readiness_is_a_live_probe_not_a_cached_success(self):
        self.assertIn("/v1/ai-ready", self.api)
        self.assertIn("hard live probe", self.api)
        self.assertIn("remote_ai_ready = None", self.api)
        self.assertNotIn("cache_hit provider=", self.api)

    def test_production_local_fallback_is_configurable_and_not_environment_blocked(self):
        self.assertIn("allow_local_fallback = requested_local_fallback and config.local_fallback_enabled", self.api)
        self.assertNotIn("local_fallback_blocked_in_production", self.api)


    def test_response_meta_exposes_evidence_grade_and_sources(self):
        self.assertIn('evidence_grade: str | None = None', self.api)
        self.assertIn('web_sources_details: list[dict[str, Any]]', self.api)


    def test_chat_request_normalizes_text_fields_before_validation(self):
        self.assertIn('from pydantic import BaseModel, Field, field_validator', self.api)
        self.assertIn('field_validator("message", "user_id", "conversation_id", "request_id", "personality", "voice_tone", mode="before")', self.api)
        self.assertIn('return value.strip() if isinstance(value, str) else value', self.api)
        self.assertIn('message: str = Field(min_length=1, max_length=20_000)', self.api)

    def test_global_http_responses_are_marked_no_store(self):
        self.assertIn('response.headers.setdefault("Cache-Control", "no-store")', self.api)
        self.assertIn('apply_security_headers(response)', self.api)

    def test_chat_response_meta_alias_remains_stable(self):
        self.assertIn('meta: ResponseMeta = Field(alias="_meta")', self.api)
        self.assertIn('model_config = {"populate_by_name": True}', self.api)
        self.assertIn('web_searches: list[str]', self.api)

    def test_local_fallback_metadata_is_explicit_and_consistent(self):
        self.assertIn('"used_local_fallback":True', self.api)
        self.assertIn('"web_searches":[]', self.api)
        self.assertIn('"web_sources_details":[]', self.api)
        self.assertIn('"verification_ok":False', self.api)
        self.assertIn('"evidence_grade":None', self.api)

    def test_stream_crash_emits_structured_error_event(self):
        self.assertIn('yield "event: error\\n"', self.api)
        self.assertIn('"reason": "stream_crash"', self.api)
        self.assertIn('"final_reason": "stream_crash"', self.api)
        self.assertNotIn('[NEXO_STREAM_CRASH]', self.api)

    def test_replication_payload_is_bounded_before_json_parse(self):
        self.assertIn('_MAX_REPLICATION_BODY_BYTES = 2_000_000', self.api)
        self.assertIn('if len(raw) > _MAX_REPLICATION_BODY_BYTES:', self.api)
        self.assertIn('replication_payload_too_large', self.api)

    def test_replication_requires_explicit_protocol_version(self):
        self.assertIn('request.headers.get("X-C33-Replication-Version", "").strip()', self.api)
        self.assertIn('if version != "1":', self.api)
        self.assertIn('unsupported_replication_version', self.api)

    def test_capabilities_endpoint_is_safe_metadata(self):
        self.assertIn('@app.get("/v1/capabilities")', self.api)
        self.assertIn('safe capability metadata', self.api)
        self.assertNotIn('CONTROL_TOKEN', self.api.split('@app.get("/v1/capabilities")', 1)[1].split('@app.get("/v1/metrics")', 1)[0])

    def test_http_and_stream_transport_errors_use_nested_context(self):
        self.assertGreaterEqual(self.providers.count("cause = exc.__cause__"), 2)
        self.assertGreaterEqual(self.providers.count("temporary failure in name resolution"), 2)

if __name__ == "__main__":
    unittest.main()
