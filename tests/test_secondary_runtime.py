import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("PORT", "8080")
os.environ.setdefault("SECRET_KEYS", "test-secret-key-123456")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("AI_ZERO_COST_MODE", "true")
os.environ.setdefault("MODEL_BASE_URL", "https://vireonix.ai/v1")
os.environ.setdefault("REQUIRE_PROVIDER_REDUNDANCY", "true")
sys.path.insert(0, "src")

from api import replication_status, ready


class FakeSecondaryState:
    async def database_ping(self):
        return True

    async def replication_pending_count(self):
        return 0

    async def replication_integrity(self):
        return {
            "total_messages": 12,
            "unique_message_ids": 12,
            "message_id_digest": "a" * 64,
            "message_digest": "b" * 64,
        }


class SecondaryRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_ready_does_not_require_remote_ai_cascade(self):
        import api

        fake = FakeSecondaryState()
        with patch.object(api.config, "role", "secondary"), patch.object(api, "state", fake), patch.object(api, "cascade", None):
            response = await ready()

        self.assertEqual(response.status, "ready")
        self.assertEqual(response.database, "ok")
        self.assertEqual(response.provider_count, 0)
        self.assertFalse(response.peer_configured)

    async def test_replication_status_identifies_secondary_and_is_quiesced(self):
        import api

        fake = FakeSecondaryState()
        with patch.object(api.config, "role", "secondary"), patch.object(api, "state", fake):
            response = await replication_status()

        self.assertEqual(response["backend_role"], "secondary")
        self.assertEqual(response["peer_status"], "NOT_CONFIGURED")
        self.assertEqual(response["replication_pending"], 0)
        self.assertTrue(response["quiesced"])
        self.assertEqual(response["total_messages"], 12)
        self.assertEqual(response["unique_message_ids"], 12)


if __name__ == "__main__":
    unittest.main()
