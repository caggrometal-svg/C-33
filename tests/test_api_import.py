import importlib
import os
import unittest


class ApiImportTests(unittest.TestCase):
    def test_api_imports_and_preserves_meta_alias(self):
        os.environ.setdefault("PORT", "10000")
        os.environ.setdefault("SECRET_KEYS", "test-secret-key-123456")
        os.environ.setdefault("APP_ENV", "test")
        os.environ.setdefault("REQUIRE_PROVIDER_REDUNDANCY", "false")
        api = importlib.import_module("api")

        model = api.ChatResponse(
            status="ok",
            service="C-33",
            user_id="u",
            conversation_id="c",
            request_id="r",
            synthesis="ok",
            web_searches=[],
            meta=api.ResponseMeta(
                provider_used="test",
                model="test-model",
                failover_triggered=False,
                latency_ms=1,
                final_reason="success",
                system_status="AI_READY",
                backend_role="primary",
                backend_url="https://iac33-backup-production.up.railway.app",
                request_id="r",
                conversation_id="c",
                memory_sync="SYNCED",
                peer_status="ONLINE",
                provider_attempts=1,
                used_local_fallback=False,
            ),
        )
        payload = model.model_dump(by_alias=True)
        self.assertIn("_meta", payload)
        self.assertNotIn("meta", payload)


if __name__ == "__main__":
    unittest.main()
